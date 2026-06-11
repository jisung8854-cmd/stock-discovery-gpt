from dataclasses import dataclass
from typing import Any

import httpx

AUTH_FAILURE_MESSAGE = "stock-data-gateway authorization failed"


@dataclass(frozen=True)
class GatewayResult:
    data: Any = None
    error: str | None = None
    auth_failed: bool = False

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
        bearer_token: str | None = None,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token.strip() if bearer_token else None
        self.timeout = timeout
        self.transport = transport

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
            return GatewayResult(error=AUTH_FAILURE_MESSAGE, auth_failed=True)

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, **kwargs)
                if response.status_code in {401, 403}:
                    return GatewayResult(error=AUTH_FAILURE_MESSAGE, auth_failed=True)
                response.raise_for_status()
                return GatewayResult(data=response.json())
        except (httpx.HTTPError, ValueError):
            return GatewayResult(error=f"stock-data-gateway request failed for {path}")
