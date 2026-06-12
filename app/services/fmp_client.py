import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class FMPEndpointResult:
    """Result for one FMP endpoint call.

    Endpoint failures are represented as data=None plus an error message so callers can
    continue with partial data instead of crashing the score response.
    """

    data: dict[str, Any] | list[dict[str, Any]] | None
    error: str | None = None
    error_type: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class FMPClient:
    """Financial Modeling Prep client for US-listed stock data."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://financialmodelingprep.com/api/v3",
        timeout_seconds: float = 15,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("FMP_API_KEY", "")).strip() or None
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    @property
    def is_configured(self) -> bool:
        """Return whether an FMP API key is available without exposing its value."""
        return self.api_key is not None

    async def get_company_profile(self, ticker: str) -> FMPEndpointResult:
        result = await self._get_list_endpoint(f"/profile/{ticker}")
        if not result.ok or not isinstance(result.data, list):
            return result
        return FMPEndpointResult(data=result.data[0] if result.data else {})

    async def get_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            f"/income-statement/{ticker}", params={"period": period, "limit": limit}
        )

    async def get_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            f"/balance-sheet-statement/{ticker}",
            params={"period": period, "limit": limit},
        )

    async def get_cash_flow_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            f"/cash-flow-statement/{ticker}", params={"period": period, "limit": limit}
        )

    async def get_key_metrics(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            f"/key-metrics/{ticker}", params={"period": period, "limit": limit}
        )

    async def get_ratios(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            f"/ratios/{ticker}", params={"period": period, "limit": limit}
        )

    async def get_quote(self, ticker: str) -> FMPEndpointResult:
        result = await self._get_list_endpoint(f"/quote/{ticker}")
        if not result.ok or not isinstance(result.data, list):
            return result
        return FMPEndpointResult(data=result.data[0] if result.data else {})

    async def _get_list_endpoint(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> FMPEndpointResult:
        if not self.api_key:
            return FMPEndpointResult(
                data=None,
                error="FMP API key is not configured.",
                error_type="fmp_auth_failed_or_plan_limited",
            )

        request_params: dict[str, str | int] = {"apikey": self.api_key}
        if params:
            request_params.update(params)

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=request_params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            return FMPEndpointResult(
                data=None, error=f"FMP timeout for {path}", error_type="fmp_timeout"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                return FMPEndpointResult(
                    data=None,
                    error="FMP authentication failed or endpoint not allowed by plan.",
                    error_type="fmp_auth_failed_or_plan_limited",
                )
            return FMPEndpointResult(
                data=None,
                error=f"FMP HTTP {exc.response.status_code} for {path}",
                error_type="fmp_endpoint_unavailable",
            )
        except httpx.HTTPError:
            return FMPEndpointResult(
                data=None,
                error=f"FMP network error for {path}",
                error_type="fmp_endpoint_unavailable",
            )
        except ValueError:
            return FMPEndpointResult(
                data=None,
                error=f"FMP returned invalid JSON for {path}",
                error_type="fmp_invalid_response",
            )

        if isinstance(payload, dict) and self._is_fmp_error_payload(payload):
            return FMPEndpointResult(
                data=None, error=f"FMP API error for {path}", error_type="fmp_endpoint_unavailable"
            )
        if isinstance(payload, list):
            return FMPEndpointResult(data=payload)
        if isinstance(payload, dict):
            return FMPEndpointResult(data=payload)
        return FMPEndpointResult(
            data=None,
            error=f"FMP returned unsupported payload for {path}",
            error_type="fmp_invalid_response",
        )

    def _is_fmp_error_payload(self, payload: dict[str, Any]) -> bool:
        return "Error Message" in payload or payload.get("status") == "error"
