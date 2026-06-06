from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_render_friendly_app_information() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["health_url"] == "/health"
    assert payload["openapi_url"] == "/openapi.json"
