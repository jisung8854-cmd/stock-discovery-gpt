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
    """Normalize common gateway snapshot/DART profile shapes."""
    raw = raw or {}
    payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    company = _nested_dict(payload, "company", "profile")
    quote = _nested_dict(payload, "quote", "market_data", "snapshot")
    sources = (company, quote, payload, raw)
    normalized_ticker = _first_value(*sources, keys=("ticker", "symbol", "stock_code")) or ticker
    market_cap = _first_number(*sources, keys=("market_cap", "marketCap", "mktCap"))
    price = _first_number(*sources, keys=("price", "current_price", "currentPrice"))
    return CompanySummary(
        ticker=str(normalized_ticker).upper(),
        market=market,
        name=str(
            _first_value(*sources, keys=("name", "company_name", "companyName", "corp_name"))
            or normalized_ticker
        ),
        sector=_optional_string(_first_value(*sources, keys=("sector",))),
        industry=_optional_string(_first_value(*sources, keys=("industry",))),
        market_cap=market_cap,
        price=price,
        currency=_optional_string(_first_value(*sources, keys=("currency",))),
    )


def resolved_stock_code(raw: Any, fallback: str) -> str:
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        return fallback
    nested = _nested_dict(raw, "result", "company", "data")
    value = _first_value(nested, raw, keys=("stock_code", "ticker", "symbol", "code"))
    return str(value or fallback).zfill(6)


def _nested_dict(raw: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_value(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        for key in keys:
            if source.get(key) not in (None, ""):
                return source[key]
    return None
