from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_protected_endpoint_rejects_missing_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_API_BEARER_TOKEN", "test-action-token")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post("/screen", json={"market": "NASDAQ", "limit": 1})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"
    get_settings.cache_clear()


def test_protected_endpoint_rejects_invalid_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_API_BEARER_TOKEN", "test-action-token")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/screen",
        json={"market": "NASDAQ", "limit": 1},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid bearer token"
    get_settings.cache_clear()


def test_protected_endpoint_allows_valid_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_API_BEARER_TOKEN", "test-action-token")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/screen",
        json={"market": "NASDAQ", "limit": 1},
        headers={"Authorization": "Bearer test-action-token"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    get_settings.cache_clear()


def test_health_remains_public_when_bearer_token_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_API_BEARER_TOKEN", "test-action-token")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    get_settings.cache_clear()


def test_fmp_health_remains_public_when_bearer_token_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_API_BEARER_TOKEN", "test-action-token")
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/health/fmp")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    get_settings.cache_clear()
