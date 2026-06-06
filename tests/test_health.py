from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Stock Discovery GPT API",
        "environment": "development",
    }


def test_fmp_health_reports_missing_key(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.delenv("FMP_API_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/health/fmp")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "connection_success": False,
        "note": "FMP_API_KEY is not configured.",
    }
    get_settings.cache_clear()


def test_fmp_health_reports_authentication_failure_without_exposing_key(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services.fmp_client import FMPClient, FMPEndpointResult

    async def authentication_failure(self: FMPClient, ticker: str = "AAPL") -> FMPEndpointResult:
        return FMPEndpointResult(
            data=None,
            error="FMP authentication failed or endpoint not allowed by plan.",
        )

    monkeypatch.setenv("FMP_API_KEY", "health-check-secret-key")
    monkeypatch.setattr(FMPClient, "check_connection", authentication_failure)
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/health/fmp")

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "connection_success": False,
        "note": "FMP authentication failed or endpoint not allowed by plan.",
    }
    assert "health-check-secret-key" not in response.text
    get_settings.cache_clear()
