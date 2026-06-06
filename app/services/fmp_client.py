import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FMP_AUTHENTICATION_ERROR = "FMP authentication failed or endpoint not allowed by plan."


@dataclass(frozen=True)
class FMPEndpointResult:
    """Result for one FMP endpoint call.

    Endpoint failures are represented as data=None plus an error message so callers can
    continue with partial data instead of crashing the score response.
    """

    data: dict[str, Any] | list[dict[str, Any]] | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class FMPClient:
    """Financial Modeling Prep client for US-listed stock data."""

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://financialmodelingprep.com/stable",
        timeout_seconds: float = 15,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport
        logger.debug("FMP client initialized; api_key_configured=%s", self.is_configured)

    @property
    def is_configured(self) -> bool:
        """Report key presence without exposing the key value."""

        return bool(self.api_key)

    async def check_connection(self, ticker: str = "AAPL") -> FMPEndpointResult:
        """Run a lightweight quote request for deployment diagnostics."""

        return await self.get_quote(ticker)

    async def get_company_profile(self, ticker: str) -> FMPEndpointResult:
        result = await self._get_list_endpoint("/profile", params={"symbol": ticker})
        if not result.ok or not isinstance(result.data, list):
            return result
        return FMPEndpointResult(data=result.data[0] if result.data else {})

    async def get_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            "/income-statement", params={"symbol": ticker, "period": period, "limit": limit}
        )

    async def get_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            "/balance-sheet-statement",
            params={"symbol": ticker, "period": period, "limit": limit},
        )

    async def get_cash_flow_statement(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            "/cash-flow-statement", params={"symbol": ticker, "period": period, "limit": limit}
        )

    async def get_key_metrics(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            "/key-metrics", params={"symbol": ticker, "period": period, "limit": limit}
        )

    async def get_ratios(
        self, ticker: str, period: str = "annual", limit: int = 5
    ) -> FMPEndpointResult:
        return await self._get_list_endpoint(
            "/ratios", params={"symbol": ticker, "period": period, "limit": limit}
        )

    async def get_quote(self, ticker: str) -> FMPEndpointResult:
        result = await self._get_list_endpoint("/quote", params={"symbol": ticker})
        if not result.ok or not isinstance(result.data, list):
            return result
        return FMPEndpointResult(data=result.data[0] if result.data else {})

    async def _get_list_endpoint(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> FMPEndpointResult:
        if not self.is_configured:
            logger.warning("FMP request skipped; api_key_configured=False; path=%s", path)
            return FMPEndpointResult(data=None, error="FMP_API_KEY is not configured")

        api_key = self.api_key
        assert api_key is not None
        request_params: dict[str, str | int] = dict(params or {})
        request_headers = {"apikey": api_key}

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=request_params, headers=request_headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            return FMPEndpointResult(data=None, error=f"FMP timeout for {path}")
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                logger.warning(
                    "FMP authentication or plan access failure; status=%s; path=%s; "
                    "api_key_configured=%s",
                    status_code,
                    path,
                    self.is_configured,
                )
                return FMPEndpointResult(data=None, error=FMP_AUTHENTICATION_ERROR)
            logger.warning("FMP HTTP failure; status=%s; path=%s", status_code, path)
            return FMPEndpointResult(
                data=None,
                error=f"FMP HTTP {status_code} for {path}",
            )
        except httpx.HTTPError:
            logger.warning("FMP network error; path=%s", path)
            return FMPEndpointResult(data=None, error=f"FMP network error for {path}")
        except ValueError:
            return FMPEndpointResult(data=None, error=f"FMP returned invalid JSON for {path}")

        if isinstance(payload, dict) and self._is_fmp_error_payload(payload):
            logger.warning("FMP API error payload; path=%s", path)
            return FMPEndpointResult(data=None, error=f"FMP API error for {path}")
        if isinstance(payload, list):
            return FMPEndpointResult(data=payload)
        if isinstance(payload, dict):
            return FMPEndpointResult(data=payload)
        return FMPEndpointResult(data=None, error=f"FMP returned unsupported payload for {path}")

    def _is_fmp_error_payload(self, payload: dict[str, Any]) -> bool:
        return "Error Message" in payload or payload.get("status") == "error"
