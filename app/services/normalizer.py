from typing import Any

from app.models.common import Market
from app.models.company import CompanySummary


def normalize_company(raw: dict[str, Any], market: Market, ticker: str) -> CompanySummary:
    return CompanySummary(
        ticker=ticker.upper(),
        market=market,
        name=str(raw.get("name", f"Mock {ticker.upper()} Corporation")),
        sector=raw.get("sector", "Technology"),
        industry=raw.get("industry", "Software"),
        market_cap=raw.get("market_cap", 50_000_000_000),
    )


def normalize_fmp_company(
    profile: dict[str, Any] | None,
    quote: dict[str, Any] | None,
    market: Market,
    ticker: str,
) -> CompanySummary:
    profile = profile or {}
    quote = quote or {}
    market_cap = _first_number(profile, quote, keys=("mktCap", "marketCap"))
    return CompanySummary(
        ticker=str(profile.get("symbol") or quote.get("symbol") or ticker).upper(),
        market=market,
        name=str(profile.get("companyName") or quote.get("name") or ticker.upper()),
        sector=_optional_string(profile.get("sector")),
        industry=_optional_string(profile.get("industry")),
        market_cap=market_cap,
    )


def _first_number(*sources: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, int | float):
                return float(value)
    return None


def _optional_string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def normalize_dart_company(
    overview: dict[str, Any] | None,
    market: Market,
    stock_code: str,
) -> CompanySummary:
    overview = overview or {}
    normalized_stock_code = str(
        overview.get("stock_code") or overview.get("stock_code") or stock_code
    ).zfill(6)
    return CompanySummary(
        ticker=normalized_stock_code,
        market=market,
        name=str(
            overview.get("corp_name") or overview.get("corp_name_eng") or normalized_stock_code
        ),
        sector=None,
        industry=None,
        market_cap=None,
    )


def normalize_gateway_company(
    raw: dict[str, Any] | None,
    market: Market,
    ticker: str,
) -> CompanySummary:
    """Normalize common gateway snapshot/DART profile shapes without inventing data."""
    raw = raw or {}
    return CompanySummary(
        ticker=str(gateway_value(raw, "ticker", "symbol", "stock_code", "code") or ticker).upper(),
        market=market,
        name=str(
            gateway_value(raw, "name", "company_name", "companyName", "corp_name")
            or ticker.upper()
        ),
        sector=_optional_string(gateway_value(raw, "sector")),
        industry=_optional_string(gateway_value(raw, "industry")),
        market_cap=gateway_number(raw, "market_cap", "marketCap", "mktCap"),
        price=gateway_number(raw, "price", "current_price", "currentPrice"),
        currency=_optional_string(gateway_value(raw, "currency")),
    )


def resolved_stock_code(raw: Any, fallback: str) -> str:
    value = gateway_value(raw, "stock_code", "ticker", "symbol", "code")
    return str(value or fallback).zfill(6)


def gateway_value(raw: Any, *keys: str) -> Any:
    """Find the first non-empty value for gateway aliases in nested mappings/lists."""
    if isinstance(raw, dict):
        for key in keys:
            if raw.get(key) not in (None, ""):
                return raw[key]
        for value in raw.values():
            found = gateway_value(value, *keys)
            if found not in (None, ""):
                return found
    elif isinstance(raw, list):
        for value in raw:
            found = gateway_value(value, *keys)
            if found not in (None, ""):
                return found
    return None


def gateway_number(raw: Any, *keys: str) -> float | None:
    value = gateway_value(raw, *keys)
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
