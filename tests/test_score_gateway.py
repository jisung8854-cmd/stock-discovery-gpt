from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import score
from app.main import app
from app.services.gateway_client import GatewayResult

client = TestClient(app)


class StubGatewayClient:
    calls: list[tuple[Any, ...]] = []
    fail_snapshot = False
    snapshot_error = "stock-data-gateway request failed for /v1/market-snapshot"
    omit_valuation = False
    direct_snapshot = False
    expected_bearer_token: str | None = None

    def __init__(self, base_url: str, bearer_token: str | None = None) -> None:
        self.calls.append(("base_url", base_url))
        self.calls.append(("gateway_bearer_token_configured", bearer_token is not None))
        if self.expected_bearer_token is not None:
            assert bearer_token == self.expected_bearer_token

    async def get_market_snapshot(self, symbol: str, market: str) -> GatewayResult:
        self.calls.append(("snapshot", symbol, market))
        if self.fail_snapshot:
            return GatewayResult(error=self.snapshot_error)
        if self.direct_snapshot:
            return GatewayResult(data={
                "ticker": symbol,
                "name": "NVIDIA Corporation",
                "price": 140.0,
                "market_cap": 3_400_000_000_000,
                "enterprise_value": 3_300_000_000_000,
                "fcf_yield": 0.045,
                "ev_to_ebitda": 28.0,
                "roe": 0.75,
                "roic": 0.55,
                "current_ratio": 3.5,
                "net_debt_to_ebitda": 0.1,
                "capex_to_revenue": 0.04,
            })
        data: dict[str, Any] = {
            "company": {
                "symbol": symbol,
                "name": "Apple Inc.",
                "marketCap": 3_000_000_000_000,
                "currency": "USD",
            },
            "quote": {"price": 205.0},
            "metrics": {
                "revenue_growth": 0.16,
                "gross_margin": 0.65,
                "operating_margin": 0.35,
                "net_margin": 0.24,
                "fcf_margin": 0.24,
                "fcf_yield": 0.07,
                "roic": 0.24,
                "roe": 0.3,
                "debt_to_equity": 0.1,
                "current_ratio": 2.4,
            },
            "valuation": {
                "pe_ratio": 16,
                "price_to_book": 2,
                "ev_to_ebitda": 10,
                "margin_of_safety": 0.25,
            },
        }
        if self.omit_valuation:
            data.pop("valuation")
        return GatewayResult(data=data)

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
    StubGatewayClient.snapshot_error = "stock-data-gateway request failed for /v1/market-snapshot"
    StubGatewayClient.omit_valuation = False
    StubGatewayClient.direct_snapshot = False
    StubGatewayClient.expected_bearer_token = None


def test_nasdaq_score_uses_gateway_market_snapshot(monkeypatch: Any) -> None:
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert ("snapshot", "AAPL", "NASDAQ") in StubGatewayClient.calls
    assert body["company"]["name"] == "Apple Inc."
    assert body["company"]["price"] == 205.0
    assert body["metrics"]["revenue_growth"] == 0.16
    assert body["valuation"]["pe_ratio"] == 16
    assert body["data_basis"] == {
        "source": "stock-data-gateway",
        "is_mock": False,
        "reliability": 0.7,
        "notes": [],
    }
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


def test_score_passes_configured_bearer_token_to_gateway_client(monkeypatch: Any) -> None:
    StubGatewayClient.expected_bearer_token = "configured-test-token"
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)
    monkeypatch.setattr(
        score,
        "get_settings",
        lambda: SimpleNamespace(
            stock_data_gateway_url="https://gateway.example",
            stock_data_gateway_bearer_token="configured-test-token",
        ),
    )

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    assert ("gateway_bearer_token_configured", True) in StubGatewayClient.calls


def test_gateway_auth_failure_returns_sanitized_flag_and_note(monkeypatch: Any) -> None:
    StubGatewayClient.fail_snapshot = True
    StubGatewayClient.snapshot_error = "gateway_auth_failed"
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert "gateway_auth_failed" in body["risk_flags"]
    assert "stock-data-gateway authorization failed" in body["data_basis"]["notes"]
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


def test_missing_gateway_token_returns_sanitized_auth_failure(monkeypatch: Any) -> None:
    StubGatewayClient.fail_snapshot = True
    StubGatewayClient.snapshot_error = "gateway_auth_missing"
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert "gateway_auth_failed" in body["risk_flags"]
    assert "stock-data-gateway authorization is not configured" in body["data_basis"]["notes"]


def test_gateway_failure_returns_partial_result(monkeypatch: Any) -> None:
    StubGatewayClient.fail_snapshot = True
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["data_basis"]["reliability"] == 0.2
    assert "gateway_unavailable" in body["risk_flags"]
    assert "fmp_data_unavailable" in body["risk_flags"]
    assert "low_data_reliability" in body["risk_flags"]
    assert body["hard_fail"] is True
    assert body["final_label"] != "elite_candidate"


def test_valuation_signal_in_metrics_prevents_missing_flag(monkeypatch: Any) -> None:
    StubGatewayClient.omit_valuation = True
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/NASDAQ/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["data_basis"]["reliability"] == 0.7
    assert "valuation_data_missing" not in body["risk_flags"]
    assert "low_data_reliability" not in body["risk_flags"]
    assert body["hard_fail"] is False
    assert body["final_label"] != "elite_candidate"


def test_direct_snapshot_metrics_drive_scores_flags_and_identity(monkeypatch: Any) -> None:
    StubGatewayClient.direct_snapshot = True
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    body = client.post("/score/NASDAQ/NVDA").json()

    assert body["company"]["ticker"] == "NVDA"
    assert body["company"]["name"] == "NVIDIA Corporation"
    assert "AAPL" not in str(body)
    assert body["metrics"]["fcf_yield"] == 0.045
    assert body["metrics"]["roe"] == 0.75
    assert body["metrics"]["roic"] == 0.55
    assert body["metrics"]["current_ratio"] == 3.5
    assert body["valuation"]["ev_to_ebitda"] == 28.0
    assert "financial_metrics_missing" not in body["risk_flags"]
    assert "valuation_data_missing" not in body["risk_flags"]
    assert "low_data_reliability" not in body["risk_flags"]
    assert body["data_basis"]["reliability"] >= 0.7
    assert body["scores"]["total_score"] != 50.0
    assert all(body["scores"][key] != 50.0 for key in ("BQS", "PAS", "VDS", "EES"))


def test_korean_stock_code_loads_mocked_company_and_disclosures(monkeypatch: Any) -> None:
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
    assert "dart_data_unavailable" not in body["risk_flags"]
    assert "financial_metrics_missing" in body["risk_flags"]
    assert "valuation_data_missing" in body["risk_flags"]
    assert body["hard_fail"] is False
    assert body["final_label"] == "watchlist"


def test_korean_company_query_uses_resolver(monkeypatch: Any) -> None:
    monkeypatch.setattr(score, "GatewayClient", StubGatewayClient)

    response = client.post("/score/KOSPI/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90")

    assert response.status_code == 200
    assert ("resolve", "삼성전자") in StubGatewayClient.calls
    assert ("company", "005930") in StubGatewayClient.calls
