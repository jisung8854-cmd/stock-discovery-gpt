import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.services.gateway_client import GatewayClient


def test_gateway_client_sends_authorization_header_for_market_snapshot() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://gateway.example/v1/market-snapshot")
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer gateway-test-token"
        assert request.read() == b'{"symbol":"AAPL","market":"NASDAQ"}'
        return httpx.Response(200, json={"company": {"symbol": "AAPL"}})

    settings = Settings(stock_data_gateway_url="https://gateway.example")
    client = GatewayClient(
        settings.stock_data_gateway_url,
        transport=httpx.MockTransport(handler),
        bearer_token="gateway-test-token",
    )
    result = asyncio.run(client.get_market_snapshot("AAPL", "NASDAQ"))

    assert client.gateway_bearer_token_configured is True
    assert result.ok
    assert result.data["company"]["symbol"] == "AAPL"


def test_gateway_client_returns_safe_failure_when_bearer_token_is_missing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("Gateway request must not be sent without a bearer token")

    client = GatewayClient(
        "https://gateway.example",
        transport=httpx.MockTransport(handler),
        bearer_token=" ",
    )
    result = asyncio.run(client.get_market_snapshot("AAPL", "NASDAQ"))

    assert client.gateway_bearer_token_configured is False
    assert not result.ok
    assert result.error == "gateway_auth_missing"


@pytest.mark.parametrize("status_code", [401, 403])
def test_gateway_client_sanitizes_gateway_auth_failure(status_code: int) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="secret-bearing upstream detail")

    client = GatewayClient(
        "https://gateway.example",
        transport=httpx.MockTransport(handler),
        bearer_token="gateway-test-token",
    )
    result = asyncio.run(client.get_dart_company_profile("005930"))

    assert not result.ok
    assert result.error == "gateway_auth_failed"
    assert "secret" not in result.error
    assert "gateway-test-token" not in result.error


def test_gateway_client_sanitizes_gateway_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("secret-bearing upstream detail")

    client = GatewayClient(
        "https://gateway.example",
        transport=httpx.MockTransport(handler),
        bearer_token="gateway-test-token",
    )
    result = asyncio.run(client.get_dart_company_profile("005930"))

    assert not result.ok
    assert result.error == "stock-data-gateway request failed for /kr/dart/company"


def test_settings_reads_stock_data_gateway_configuration_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STOCK_DATA_GATEWAY_URL", "https://env-gateway.example")
    monkeypatch.setenv("STOCK_DATA_GATEWAY_BEARER_TOKEN", "env-gateway-token")

    settings = Settings()

    assert settings.stock_data_gateway_url == "https://env-gateway.example"
    assert settings.stock_data_gateway_bearer_token == "env-gateway-token"
