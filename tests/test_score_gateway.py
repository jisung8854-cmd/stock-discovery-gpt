from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import score
from app.main import app
from app.services.gateway_client import GatewayResult

client = TestClient(app)


class StubGatewayClient:
    calls: list[tuple[Any, ...]] = []
    fail_snapshot = False

    def __init__(self, base_url: str) -> None:
        self.calls.append(("base_url", base_url))

    async def get_market_snapshot(self, symbol: str, market: str) -> GatewayResult:
        self.calls.append(("snapshot", symbol, market))
        if self.fail_snapshot:
            return GatewayResult(error="stock-data-gateway request failed for /v1/market-snapshot")
        return GatewayResult(
            data={
                "company": {
                    "symbol": symbol,
                    "name": "Apple Inc.",
                    "marketCap": 3_000_000_000_000,
                    "currency": "USD",
                },
                "quote": {"price": 205.0},
            }
        )

    async def resolve_korean_ticker(self, query: str) -> GatewayResult:
        self.calls.append(("resolve", query))
        return GatewayResult(data={"stock_code": "005930"})

    async def get_dart_company_profile(self, stock_code: str) -> GatewayResult:
        self.calls.append(("company", stock_code))
        return GatewayResult(data={"stock_code": stock_code, "corp_name": "삼성전자"})

    async def get_dart_disclosures(self, stock_code: str, limit: int = 20) -> GatewayResult:
        self.calls.append(("disclosures", stock_code, limit))
        return GatewayResult(data=[{"report_nm": "유상증자결정"}])


def setup_function() -> None:
    StubGatewayClient.calls = []
    StubGatewayClient.fail_snapshot = False


def test_nasdaq_score_uses_gateway_market_snapshot(monkeypatch: Any) -> None:
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert ("snapshot", "AAPL", "NASDAQ") in StubGatewayClient.calls
    assert body["company"]["name"] == "Apple Inc."
    assert body["company"]["price"] == 205.0
    assert body["data_basis"]["source"] == "stock-data-gateway"
    assert "partial_gateway_data" in body["risk_flags"]
    assert set(body) == {
        "company",
        "data_basis",
        "metrics",
        "valuation",
        "scores",
        "risk_flags",
        "hard_fail",
        "final_label",
    }


def test_gateway_failure_returns_partial_result(monkeypatch: Any) -> None:
    StubGatewayClient.fail_snapshot = True
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["data_basis"]["reliability"] == 0.2
    assert "gateway_unavailable" in body["risk_flags"]
    assert "fmp_data_unavailable" in body["risk_flags"]
    assert body["final_label"] != "elite_candidate"


def test_korean_query_resolves_and_loads_dart_gateway_data(monkeypatch: Any) -> None:
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/KOSPI/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90")

    assert response.status_code == 200
    body = response.json()
    assert ("resolve", "삼성전자") in StubGatewayClient.calls
    assert ("company", "005930") in StubGatewayClient.calls
    assert ("disclosures", "005930", 20) in StubGatewayClient.calls
    assert body["company"]["ticker"] == "005930"
    assert body["company"]["name"] == "삼성전자"
    assert "disclosure_risk_detected" in body["risk_flags"]
