from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import score
from app.main import app
from app.services.gateway_client import GatewayResult

client = TestClient(app)


class StubGatewayClient:
    calls: list[tuple[Any, ...]] = []
    snapshot_mode = "complete"

    def __init__(self, base_url: str) -> None:
        self.calls.append(("base_url", base_url))

    async def get_market_snapshot(self, symbol: str, market: str) -> GatewayResult:
        self.calls.append(("snapshot", symbol, market))
        if self.snapshot_mode == "failure":
            return GatewayResult(error="stock-data-gateway request failed for /v1/market-snapshot")
        data = {
            "source": "fmp-via-stock-data-gateway",
            "company": {
                "symbol": symbol,
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "marketCap": 3_000_000_000_000,
                "currency": "USD",
            },
            "quote": {"price": 205.0, "pe": 31.0},
            "metrics": {
                "revenueGrowth": 0.08,
                "grossMargin": 0.46,
                "operatingMargin": 0.31,
                "netMargin": 0.24,
                "freeCashFlow": 100_000_000_000,
                "freeCashFlowMargin": 0.25,
                "fcfYield": 0.033,
                "returnOnEquity": 1.5,
                "returnOnInvestedCapital": 0.55,
                "debtToEquity": 1.4,
                "currentRatio": 0.9,
            },
            "valuation": {"forwardPE": 28.0, "evToEbitda": 24.0},
        }
        if self.snapshot_mode == "partial_valuation":
            data["valuation"] = {}
            data["quote"] = {"price": 205.0}
        return GatewayResult(data=data)

    async def resolve_korean_ticker(self, query: str) -> GatewayResult:
        self.calls.append(("resolve", query))
        return GatewayResult(data={"stock_code": "005930"})

    async def get_dart_company_profile(self, stock_code: str) -> GatewayResult:
        self.calls.append(("company", stock_code))
        return GatewayResult(
            data={
                "source": "dart-via-stock-data-gateway",
                "stock_code": stock_code,
                "corp_name": "삼성전자",
                "sector": "Technology",
            }
        )

    async def get_dart_disclosures(self, stock_code: str, limit: int = 20) -> GatewayResult:
        self.calls.append(("disclosures", stock_code, limit))
        return GatewayResult(data=[{"report_nm": "유상증자결정"}])


def setup_function() -> None:
    StubGatewayClient.calls = []
    StubGatewayClient.snapshot_mode = "complete"


def test_aapl_gateway_snapshot_maps_analysis_without_hard_fail(monkeypatch: Any) -> None:
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert ("snapshot", "AAPL", "NASDAQ") in StubGatewayClient.calls
    assert body["company"] == {
        "ticker": "AAPL",
        "market": "NASDAQ",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3_000_000_000_000.0,
        "price": 205.0,
        "currency": "USD",
    }
    assert body["data_basis"]["source"] == "fmp-via-stock-data-gateway"
    assert body["data_basis"]["reliability"] >= 0.75
    assert body["metrics"]["revenue_growth"] == 0.08
    assert body["metrics"]["fcf_margin"] == 0.25
    assert body["valuation"]["per"] == 31.0
    assert body["valuation"]["forward_per"] == 28.0
    assert body["valuation"]["ev_ebitda"] == 24.0
    assert body["hard_fail"] is False
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


def test_gateway_failure_is_low_reliability_hard_fail(monkeypatch: Any) -> None:
    StubGatewayClient.snapshot_mode = "failure"
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["data_basis"]["reliability"] < 0.5
    assert body["hard_fail"] is True
    assert "gateway_unavailable" in body["risk_flags"]
    assert "low_data_reliability" in body["risk_flags"]
    assert body["final_label"] == "reject"


def test_partial_valuation_data_returns_nulls_without_crashing(monkeypatch: Any) -> None:
    StubGatewayClient.snapshot_mode = "partial_valuation"
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NYSE/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["valuation"]["per"] is None
    assert body["valuation"]["forward_per"] is None
    assert body["hard_fail"] is False
    assert "valuation_data_missing" in body["risk_flags"]
    assert "partial_gateway_data" in body["risk_flags"]


def test_kospi_stock_code_loads_mocked_dart_gateway_data(monkeypatch: Any) -> None:
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/KOSPI/005930")

    assert response.status_code == 200
    body = response.json()
    assert not any(call[0] == "resolve" for call in StubGatewayClient.calls)
    assert ("company", "005930") in StubGatewayClient.calls
    assert ("disclosures", "005930", 20) in StubGatewayClient.calls
    assert body["company"]["ticker"] == "005930"
    assert body["company"]["name"] == "삼성전자"
    assert "disclosure_risk_detected" in body["risk_flags"]
