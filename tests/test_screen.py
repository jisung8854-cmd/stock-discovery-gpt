from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import screen as screen_route
from app.main import app
from app.models.common import FinalLabel, Market
from app.models.scoring import Candidate

client = TestClient(app)


def test_kospi_screen_with_zero_market_cap_filter_returns_safe_fallback() -> None:
    response = client.post("/screen", json={"market": "KOSPI", "min_market_cap": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] > 0
    assert "partial_gateway_data" in body["risk_flags"]
    assert all(candidate["market_cap"] is None for candidate in body["candidates"])
    assert all(candidate["market_cap_unit"] == "KRW" for candidate in body["candidates"])


def test_us_candidates_use_usd_market_cap_unit() -> None:
    response = client.post("/screen", json={"market": "NASDAQ", "min_market_cap": 0})

    assert response.status_code == 200
    assert all(candidate["market_cap_unit"] == "USD" for candidate in response.json()["candidates"])


def test_mock_candidates_are_explicitly_low_reliability_and_never_elite() -> None:
    response = client.get("/candidates/top", params={"market": "KOSPI", "limit": 3})

    assert response.status_code == 200
    for candidate in response.json():
        assert candidate["is_mock"] is True
        assert candidate["data_source"] == "mock"
        assert candidate["data_reliability"] == 0.25
        assert candidate["data_reliability_label"] == "low"
        assert "mock_data_used" in candidate["risk_flags"]
        assert candidate["final_label"] != "elite_candidate"


def test_positive_market_cap_filter_excludes_candidates_with_unknown_market_cap() -> None:
    response = client.post("/screen", json={"market": "KOSPI", "min_market_cap": 1})

    assert response.status_code == 200
    assert response.json()["candidates"] == []


def test_get_top_candidates_returns_sanitized_fallback_when_provider_raises(
    monkeypatch: Any,
) -> None:
    def raise_client_response_error(*args: Any, **kwargs: Any) -> list[Candidate]:
        raise RuntimeError("ClientResponseError: secret internal URL and API key")

    monkeypatch.setattr(screen_route.ScreenerService, "top_candidates", raise_client_response_error)

    response = client.get("/candidates/top", params={"market": "KOSPI", "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert "gateway_unavailable" in body[0]["risk_flags"]
    assert "partial_gateway_data" in body[0]["risk_flags"]
    assert "secret" not in str(body).lower()
    assert "internal url" not in str(body).lower()


def test_candidate_optional_metadata_does_not_change_existing_required_fields() -> None:
    candidate = Candidate(
        ticker="AAPL",
        market=Market.NASDAQ,
        company_name="Apple Inc.",
        market_cap=3_000_000_000_000,
        total_score=80,
        BQS=80,
        PAS=80,
        VDS=80,
        EES=80,
        data_reliability=1,
        final_label=FinalLabel.STRONG_CANDIDATE,
    )

    assert candidate.is_mock is None
    assert candidate.risk_flags == []


def test_screen_returns_sanitized_fallback_when_provider_raises(monkeypatch: Any) -> None:
    def raise_provider_error(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("gateway secret internal URL")

    monkeypatch.setattr(screen_route.ScreenerService, "screen", raise_provider_error)

    response = client.post("/screen", json={"market": "KOSDAQ", "min_market_cap": 0, "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert "gateway_unavailable" in body["risk_flags"]
    assert "secret" not in str(body).lower()
    assert "gateway_unavailable" in body["candidates"][0]["risk_flags"]


def test_score_stock_openapi_response_schema_is_unchanged() -> None:
    schema = app.openapi()
    score_response = schema["components"]["schemas"]["ScoreResponse"]

    assert set(score_response["properties"]) == {
        "company",
        "data_basis",
        "metrics",
        "valuation",
        "scores",
        "risk_flags",
        "hard_fail",
        "final_label",
    }
    assert schema["paths"]["/score/{market}/{ticker}"]["post"]["operationId"] == "scoreStock"
