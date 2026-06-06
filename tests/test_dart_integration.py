import asyncio
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import httpx

from app.core.config import Settings
from app.models.common import Market
from app.services.dart_client import DARTClient, DARTEndpointResult
from app.services.screener import ScreenerService


def test_dart_client_downloads_and_caches_corp_code_mapping() -> None:
    DARTClient._corp_code_mapping_cache = None
    call_counts = {"corp_code": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/corpCode.xml":
            call_counts["corp_code"] += 1
            return httpx.Response(200, content=_corp_code_zip_bytes())
        raise AssertionError(f"Unexpected DART request: {request.url}")

    client = DARTClient(
        api_key="test-dart-key",
        base_url="https://opendart.fss.or.kr/api",
        transport=httpx.MockTransport(handler),
    )

    first = asyncio.run(client.get_corp_code_mapping())
    second = asyncio.run(client.get_corp_code_mapping())

    assert first.ok
    assert second.ok
    assert call_counts["corp_code"] == 1
    assert first.data == second.data
    assert isinstance(first.data, dict)
    assert first.data["005930"]["corp_code"] == "00126380"


def test_dart_client_finds_company_by_stock_code_without_real_api_call() -> None:
    DARTClient._corp_code_mapping_cache = None

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/corpCode.xml":
            return httpx.Response(200, content=_corp_code_zip_bytes())
        if request.url.path == "/api/company.json":
            assert request.url.params["corp_code"] == "00126380"
            return httpx.Response(
                200,
                json={
                    "status": "000",
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                },
            )
        raise AssertionError(f"Unexpected DART request: {request.url}")

    client = DARTClient(
        api_key="test-dart-key",
        base_url="https://opendart.fss.or.kr/api",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.get_company_overview("005930"))

    assert result.ok
    assert isinstance(result.data, dict)
    assert result.data["corp_name"] == "삼성전자"
    assert result.data["stock_code"] == "005930"


def test_kospi_score_uses_dart_data_and_detects_recent_filing_risks() -> None:
    service = ScreenerService(
        settings=Settings(dart_api_key="test-dart-key"),
        dart_client=StubDARTClient(),
    )

    response = asyncio.run(service.score_stock(Market.KOSPI, "005930"))

    assert response.company.ticker == "005930"
    assert response.company.name == "삼성전자"
    assert response.data_basis.source == "dart"
    assert response.data_basis.is_mock is False
    assert response.data_basis.reliability == 1
    assert response.metrics.revenue_growth == 0.1
    assert response.metrics.operating_margin == 0.2
    assert response.metrics.debt_to_equity == 0.5
    assert "paid_in_capital_increase" in response.risk_flags
    assert "convertible_bond" in response.risk_flags
    assert "major_shareholder_change" in response.risk_flags


def test_kosdaq_score_returns_partial_dart_result_when_endpoint_fails() -> None:
    service = ScreenerService(
        settings=Settings(dart_api_key="test-dart-key"),
        dart_client=StubDARTClient(financial_error="DART API 013 for /fnlttSinglAcnt.json"),
    )

    response = asyncio.run(service.score_stock(Market.KOSDAQ, "083450"))

    assert response.data_basis.source == "dart"
    assert response.data_basis.reliability == 0.75
    assert "DART API 013" in response.data_basis.notes[0]
    assert "partial_dart_data" in response.risk_flags
    assert response.hard_fail is True


class StubDARTClient:
    def __init__(self, financial_error: str | None = None) -> None:
        self.financial_error = financial_error

    async def get_corp_code_mapping(self) -> DARTEndpointResult:
        return DARTEndpointResult(
            data={
                "005930": {
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                },
                "083450": {
                    "corp_code": "00432102",
                    "corp_name": "GST",
                    "stock_code": "083450",
                },
            }
        )

    async def get_company_overview(self, stock_code: str) -> DARTEndpointResult:
        return DARTEndpointResult(
            data={
                "corp_code": "00126380" if stock_code == "005930" else "00432102",
                "corp_name": "삼성전자" if stock_code == "005930" else "GST",
                "stock_code": stock_code,
            }
        )

    async def get_financial_statement(
        self, stock_code: str, year: int | str, report_code: str
    ) -> DARTEndpointResult:
        if self.financial_error:
            return DARTEndpointResult(data=None, error=self.financial_error)
        return DARTEndpointResult(
            data=[
                _dart_row("매출액", "110,000", "100,000"),
                _dart_row("영업이익", "22,000", "20,000"),
                _dart_row("당기순이익", "15,000", "12,000"),
                _dart_row("자산총계", "200,000", "180,000"),
                _dart_row("부채총계", "50,000", "45,000"),
                _dart_row("자본총계", "100,000", "90,000"),
            ]
        )

    async def get_recent_filings(self, stock_code: str, limit: int = 20) -> DARTEndpointResult:
        return DARTEndpointResult(
            data=[
                {"report_nm": "주요사항보고서(유상증자결정)"},
                {"report_nm": "전환사채권발행결정"},
                {"report_nm": "최대주주 변경"},
            ]
        )


def _corp_code_zip_bytes() -> bytes:
    xml = """
    <result>
      <list>
        <corp_code>00126380</corp_code>
        <corp_name>삼성전자</corp_name>
        <stock_code>005930</stock_code>
        <modify_date>20240101</modify_date>
      </list>
    </result>
    """.strip()
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return buffer.getvalue()


def _dart_row(account_name: str, current_amount: str, previous_amount: str) -> dict[str, Any]:
    return {
        "account_nm": account_name,
        "thstrm_amount": current_amount,
        "frmtrm_amount": previous_amount,
    }
