import asyncio

import httpx

from app.core.config import Settings
from app.services.gateway_client import GatewayClient


def test_gateway_client_uses_configured_base_url_for_market_snapshot() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://gateway.example/v1/market-snapshot")
        assert request.method == "POST"
        assert request.read() == b'{"symbol":"AAPL","market":"NASDAQ"}'
        return httpx.Response(200, json={"company": {"symbol": "AAPL"}})

    settings = Settings(stock_data_gateway_url="https://gateway.example")
    client = GatewayClient(
        settings.stock_data_gateway_url, transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(client.get_market_snapshot("AAPL", "NASDAQ"))

    assert result.ok
    assert result.data["company"]["symbol"] == "AAPL"


def test_gateway_client_sanitizes_gateway_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("secret-bearing upstream detail")

    client = GatewayClient("https://gateway.example", transport=httpx.MockTransport(handler))
    result = asyncio.run(client.get_dart_company_profile("005930"))

    assert not result.ok
    assert result.error == "stock-data-gateway request failed for /kr/dart/company"
