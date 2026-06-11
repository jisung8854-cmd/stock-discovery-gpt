from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class GatewayResult:
    data: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class GatewayClient:
    """Raw HTTP client for stock-data-gateway.

    Errors are converted to sanitized results so upstream scoring can return a
    partial research result without leaking request details or credentials.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        bearer_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport
        configured_token = (
            bearer_token
            if bearer_token is not None
            else get_settings().stock_data_gateway_bearer_token
        )
        self.bearer_token = configured_token.strip() if configured_token else None

    async def get_market_snapshot(self, symbol: str, market: str) -> GatewayResult:
        return await self._request(
            "POST", "/v1/market-snapshot", json={"symbol": symbol, "market": market}
        )

    async def resolve_korean_ticker(self, query: str) -> GatewayResult:
        return await self._request("GET", "/kr/resolve", params={"query": query})

    async def get_dart_company_profile(self, stock_code: str) -> GatewayResult:
        return await self._request("GET", "/kr/dart/company", params={"stock_code": stock_code})

    async def get_dart_disclosures(self, stock_code: str, limit: int = 20) -> GatewayResult:
        return await self._request(
            "GET", "/kr/dart/disclosures", params={"stock_code": stock_code, "limit": limit}
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> GatewayResult:
        if not self.bearer_token:
            return GatewayResult(error="gateway_auth_missing")

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
                headers={"Authorization": f"Bearer {self.bearer_token}"},
            ) as client:
                response = await client.request(method, path, **kwargs)
                if response.status_code in (401, 403):
                    return GatewayResult(error="gateway_auth_failed")
                response.raise_for_status()
                return GatewayResult(data=response.json())
        except (httpx.HTTPError, ValueError):
            return GatewayResult(error=f"stock-data-gateway request failed for {path}")
