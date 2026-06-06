import asyncio
import json
from typing import Any

import httpx

from app.core.config import Settings
from app.models.common import Market
from app.services.fmp_client import FMPClient, FMPEndpointResult
from app.services.screener import ScreenerService


def test_fmp_client_gets_company_profile_without_real_api_call() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/profile/AAPL"
        assert request.url.params["apikey"] == "test-key"
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "AAPL",
                    "companyName": "Apple Inc.",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "mktCap": 3_000_000_000_000,
                }
            ],
        )

    client = FMPClient(
        api_key="test-key",
        base_url="https://financialmodelingprep.com/api/v3",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.get_company_profile("AAPL"))

    assert result.ok
    assert result.data == {
        "symbol": "AAPL",
        "companyName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "mktCap": 3_000_000_000_000,
    }


def test_fmp_client_returns_error_result_on_endpoint_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    client = FMPClient(
        api_key="test-key",
        base_url="https://financialmodelingprep.com/api/v3",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.get_quote("AAPL"))

    assert not result.ok
    assert result.data is None
    assert "FMP HTTP 503" in str(result.error)


def test_us_score_uses_partial_fmp_data_and_lowers_reliability() -> None:
    service = ScreenerService(
        settings=Settings(fmp_api_key="test-key"),
        fmp_client=StubFMPClient(
            profile={
                "symbol": "AAPL",
                "companyName": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "mktCap": 3_000_000_000_000,
            },
            income=[
                {"revenue": 400_000_000_000, "operatingIncome": 120_000_000_000},
                {"revenue": 350_000_000_000, "operatingIncome": 100_000_000_000},
            ],
            balance_error="FMP HTTP 500 for /balance-sheet-statement/AAPL",
            cash_flow=[{"freeCashFlow": 90_000_000_000}],
            key_metrics=[{"peRatio": 28, "pbRatio": 6, "enterpriseValueOverEBITDA": 20}],
            ratios=[{"returnOnInvestedCapital": 0.24}],
            quote={"symbol": "AAPL", "price": 200, "marketCap": 3_000_000_000_000},
        ),
    )

    response = asyncio.run(service.score_stock(Market.NASDAQ, "AAPL"))

    assert response.company.name == "Apple Inc."
    assert response.data_basis.source == "fmp"
    assert response.data_basis.is_mock is False
    assert response.data_basis.reliability == 0.86
    assert "partial_fmp_data" in response.risk_flags
    assert response.metrics.revenue_growth == 0.1429
    assert response.metrics.operating_margin == 0.3
    assert response.metrics.free_cash_flow_margin == 0.225
    assert response.valuation.pe_ratio == 28
    assert response.final_label in {
        "elite_candidate",
        "strong_candidate",
        "watchlist",
        "reject",
    }


def test_us_score_falls_back_to_mock_without_fmp_api_key() -> None:
    service = ScreenerService(settings=Settings(fmp_api_key=None))

    response = asyncio.run(service.score_stock(Market.NASDAQ, "AAPL"))

    assert response.data_basis.source == "mock"
    assert response.data_basis.is_mock is True
    assert response.company.ticker == "AAPL"


class StubFMPClient:
    def __init__(
        self,
        *,
        profile: dict[str, Any],
        income: list[dict[str, Any]],
        balance_error: str,
        cash_flow: list[dict[str, Any]],
        key_metrics: list[dict[str, Any]],
        ratios: list[dict[str, Any]],
        quote: dict[str, Any],
    ) -> None:
        self.profile = profile
        self.income = income
        self.balance_error = balance_error
        self.cash_flow = cash_flow
        self.key_metrics = key_metrics
        self.ratios = ratios
        self.quote = quote

    async def get_company_profile(self, ticker: str) -> FMPEndpointResult:
        return FMPEndpointResult(data=json.loads(json.dumps(self.profile)))

    async def get_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return FMPEndpointResult(data=self.income)

    async def get_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return FMPEndpointResult(data=None, error=self.balance_error)

    async def get_cash_flow_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return FMPEndpointResult(data=self.cash_flow)

    async def get_key_metrics(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return FMPEndpointResult(data=self.key_metrics)

    async def get_ratios(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return FMPEndpointResult(data=self.ratios)

    async def get_quote(self, ticker: str) -> FMPEndpointResult:
        return FMPEndpointResult(data=self.quote)
