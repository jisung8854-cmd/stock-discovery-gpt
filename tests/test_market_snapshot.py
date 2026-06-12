from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import market_snapshot
from app.core.config import Settings, get_settings
from app.services.fmp_client import FMPEndpointResult


class StubFMPClient:
    def __init__(self, failures: dict[str, str] | None = None) -> None:
        self.failures = failures or {}

    def result(self, endpoint: str, data: Any) -> FMPEndpointResult:
        error_type = self.failures.get(endpoint)
        if error_type:
            return FMPEndpointResult(
                data=None,
                error="sanitized FMP endpoint failure",
                error_type=error_type,
            )
        return FMPEndpointResult(data=data)

    async def get_company_profile(self, ticker: str) -> FMPEndpointResult:
        return self.result(
            "profile",
            {
                "symbol": ticker,
                "companyName": "NVIDIA Corporation",
                "sector": "Technology",
                "industry": "Semiconductors",
                "mktCap": 3_000_000_000_000,
                "currency": "USD",
                "exchangeShortName": "NASDAQ",
            },
        )

    async def get_quote(self, ticker: str) -> FMPEndpointResult:
        return self.result(
            "quote",
            {
                "symbol": ticker,
                "name": "NVIDIA Corporation",
                "price": 150,
                "marketCap": 3_000_000_000_000,
                "volume": 100_000_000,
                "avgVolume": 95_000_000,
                "yearHigh": 160,
                "yearLow": 75,
                "pe": 40,
            },
        )

    async def get_key_metrics(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return self.result(
            "key-metrics",
            [
                {
                    "date": "2025-01-01",
                    "period": "FY",
                    "freeCashFlowYield": 0.01,
                    "returnOnEquity": 0.4,
                },
                {
                    "date": "2026-01-01",
                    "period": "FY",
                    "peRatio": 40,
                    "enterpriseValue": 3_200_000_000_000,
                    "evToSales": 25,
                    "evToOperatingCashFlow": 42,
                    "evToFreeCashFlow": 50,
                    "evToEBITDA": 30,
                    "netDebtToEBITDA": -0.5,
                    "freeCashFlowYield": 0.025,
                    "earningsYield": 0.02,
                    "returnOnEquity": 0.8,
                    "returnOnInvestedCapital": 0.5,
                    "returnOnAssets": 0.45,
                    "operatingReturnOnAssets": 0.52,
                    "returnOnTangibleAssets": 0.7,
                    "currentRatio": 3.5,
                    "investedCapital": 100_000_000_000,
                    "workingCapital": 40_000_000_000,
                    "tangibleAssetValue": 75_000_000_000,
                    "netCurrentAssetValue": 30_000_000_000,
                    "freeCashFlowToEquity": 65_000_000_000,
                    "capexToOperatingCashFlow": 0.08,
                    "capexToRevenue": 0.04,
                },
            ],
        )

    async def get_ratios(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return self.result(
            "ratios",
            [
                {
                    "returnOnEquity": 0.8,
                    "returnOnInvestedCapital": 0.5,
                    "debtEquityRatio": 0.4,
                    "currentRatio": 3.5,
                    "grossProfitMargin": 0.75,
                    "operatingProfitMargin": 0.62,
                    "netProfitMargin": 0.55,
                }
            ],
        )

    async def get_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return self.result(
            "income-statement",
            [
                {"revenue": 120_000_000_000, "eps": 3.0},
                {"revenue": 80_000_000_000, "eps": 2.0},
            ],
        )

    async def get_cash_flow_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return self.result("cash-flow-statement", [{"freeCashFlow": 60_000_000_000}])

    async def get_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return self.result("balance-sheet-statement", [{}])


def make_client(fmp_client: StubFMPClient, api_key: str = "top-secret-key") -> TestClient:
    app = FastAPI()
    app.include_router(market_snapshot.router)
    app.dependency_overrides[get_settings] = lambda: Settings(fmp_api_key=api_key)
    app.dependency_overrides[market_snapshot.get_fmp_client] = lambda: fmp_client
    return TestClient(app)


def test_market_snapshot_maps_profile_quote_key_metrics_and_ratios() -> None:
    response = make_client(StubFMPClient()).post(
        "/v1/market-snapshot", json={"symbol": "NVDA", "market": "NASDAQ"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["company"]["company_name"] == "NVIDIA Corporation"
    assert data["quote"]["price"] == 150
    assert data["valuation"]["market_cap"] == 3_000_000_000_000
    assert data["valuation"]["pe_ttm"] == 40
    assert data["valuation"]["fcf_yield"] == 0.025
    assert data["valuation"]["enterprise_value"] == 3_200_000_000_000
    assert data["valuation"]["ev_to_sales"] == 25
    assert data["valuation"]["ev_to_operating_cash_flow"] == 42
    assert data["valuation"]["ev_to_free_cash_flow"] == 50
    assert data["valuation"]["ev_to_ebitda"] == 30
    assert data["valuation"]["net_debt_to_ebitda"] == -0.5
    assert data["valuation"]["earnings_yield"] == 0.02
    assert data["financial_metrics"]["roe"] == 0.8
    assert data["financial_metrics"]["roic"] == 0.5
    assert data["financial_metrics"]["return_on_assets"] == 0.45
    assert data["financial_metrics"]["invested_capital"] == 100_000_000_000
    assert data["financial_metrics"]["free_cash_flow_to_equity"] == 65_000_000_000
    assert data["financial_metrics"]["debt_to_equity"] == 0.4
    assert data["financial_metrics"]["current_ratio"] == 3.5
    assert data["financial_metrics"]["revenue_growth"] == 0.5
    assert data["market_data"]["sector"] == "Technology"
    assert data["market_data"]["exchange"] == "NASDAQ"
    assert data["data_reliability"] >= 0.75
    assert data["data_reliability_label"] == "high"


def test_market_snapshot_returns_safe_partial_data_when_plan_limited() -> None:
    client = make_client(
        StubFMPClient(
            failures={
                "key-metrics": "fmp_auth_failed_or_plan_limited",
                "ratios": "fmp_auth_failed_or_plan_limited",
                "cash-flow-statement": "fmp_timeout",
            }
        )
    )

    response = client.post("/v1/market-snapshot", json={"symbol": "NVDA", "market": "NASDAQ"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["quote"]["price"] == 150
    assert data["financial_metrics"]["roe"] is None
    assert data["valuation"]["enterprise_value"] is None
    assert data["endpoint_errors"]["key-metrics"] == "fmp_auth_failed_or_plan_limited"
    assert "key_metrics_unavailable" in data["notes"]
    assert data["error_type"] == "fmp_auth_failed_or_plan_limited"
    assert data["data_reliability"] == 0.48
    assert data["data_reliability_label"] == "medium_low"
    assert len(data["notes"]) == 3


def test_market_snapshot_never_exposes_api_key_or_token() -> None:
    secret = "top-secret-key"
    response = make_client(StubFMPClient(), api_key=secret).post(
        "/v1/market-snapshot", json={"symbol": "NVDA", "market": "NASDAQ"}
    )

    body = response.text
    assert response.status_code == 200
    assert secret not in body
    assert "apikey" not in body.lower()
    assert "bearer" not in body.lower()


def test_fmp_client_classifies_403_without_exposing_credentials() -> None:
    import asyncio

    import httpx

    from app.services.fmp_client import FMPClient

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "plan limited"})

    result = asyncio.run(
        FMPClient(api_key="secret", transport=httpx.MockTransport(handler)).get_key_metrics("NVDA")
    )

    assert result.error_type == "fmp_auth_failed_or_plan_limited"
    assert "secret" not in str(result.error)


def test_fmp_client_classifies_timeout() -> None:
    import asyncio

    import httpx

    from app.services.fmp_client import FMPClient

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    result = asyncio.run(
        FMPClient(api_key="secret", transport=httpx.MockTransport(handler)).get_ratios("NVDA")
    )

    assert result.error_type == "fmp_timeout"


def test_key_metrics_selection_prefers_fy_or_ttm_for_same_latest_date() -> None:
    selected = market_snapshot._latest_preferred(
        FMPEndpointResult(
            data=[
                {"date": "2026-01-01", "period": "Q4", "freeCashFlowYield": 0.01},
                {"date": "2026-01-01", "period": "TTM", "freeCashFlowYield": 0.03},
                {"date": "2025-01-01", "period": "FY", "freeCashFlowYield": 0.02},
            ]
        )
    )

    assert selected["period"] == "TTM"
    assert selected["freeCashFlowYield"] == 0.03


def test_key_metrics_selection_falls_back_to_first_item_without_dates() -> None:
    first = {"period": "Q4", "freeCashFlowYield": 0.01}

    selected = market_snapshot._latest_preferred(
        FMPEndpointResult(data=[first, {"period": "FY", "freeCashFlowYield": 0.03}])
    )

    assert selected == first
