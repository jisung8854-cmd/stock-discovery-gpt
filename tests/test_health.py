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


def test_fmp_health_reports_configuration_without_exposing_key() -> None:
    from app.core.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(fmp_api_key="secret-test-key")
    try:
        client = TestClient(app)
        response = client.get("/health/fmp")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "configured": True,
        "message": "FMP_API_KEY is configured.",
    }
    assert "secret-test-key" not in response.text
