import asyncio
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.models.market_snapshot import (
    MarketSnapshotData,
    MarketSnapshotRequest,
    MarketSnapshotResponse,
    SnapshotCompany,
    SnapshotFinancialMetrics,
    SnapshotMarketData,
    SnapshotQuote,
    SnapshotValuation,
)
from app.services.fmp_client import FMPClient, FMPEndpointResult

router = APIRouter(prefix="/v1", tags=["market-data"])

_ENDPOINT_NAMES = (
    "profile",
    "quote",
    "key-metrics",
    "ratios",
    "income-statement",
    "cash-flow-statement",
    "balance-sheet-statement",
)


def get_fmp_client(settings: Settings = Depends(get_settings)) -> FMPClient:
    return FMPClient(
        api_key=settings.fmp_api_key,
        base_url=settings.fmp_base_url,
        timeout_seconds=settings.fmp_timeout_seconds,
    )


@router.post(
    "/market-snapshot",
    response_model=MarketSnapshotResponse,
    summary="Get a normalized FMP market snapshot",
)
async def market_snapshot(
    request: MarketSnapshotRequest,
    settings: Settings = Depends(get_settings),
    fmp_client: FMPClient = Depends(get_fmp_client),
) -> MarketSnapshotResponse:
    symbol = request.symbol.strip().upper()
    limit = settings.fmp_statement_limit
    results = await asyncio.gather(
        fmp_client.get_company_profile(symbol),
        fmp_client.get_quote(symbol),
        fmp_client.get_key_metrics(symbol, limit=limit),
        fmp_client.get_ratios(symbol, limit=limit),
        fmp_client.get_income_statement(symbol, limit=limit),
        fmp_client.get_cash_flow_statement(symbol, limit=limit),
        fmp_client.get_balance_sheet(symbol, limit=limit),
    )
    by_endpoint = dict(zip(_ENDPOINT_NAMES, results, strict=True))
    return MarketSnapshotResponse(data=_normalize_snapshot(symbol, by_endpoint, settings))


def _normalize_snapshot(
    symbol: str, results: Mapping[str, FMPEndpointResult], settings: Settings
) -> MarketSnapshotData:
    profile = _dict_data(results["profile"])
    quote = _dict_data(results["quote"])
    key_metrics = _first(results["key-metrics"])
    ratios = _first(results["ratios"])
    income = _list_data(results["income-statement"])
    cash_flow = _first(results["cash-flow-statement"])
    balance = _first(results["balance-sheet-statement"])
    latest_income = income[0] if income else {}
    prior_income = income[1] if len(income) > 1 else {}

    price = _number(quote, "price") or _number(profile, "price")
    market_cap = (
        _number(quote, "marketCap") or _number(profile, "mktCap") or _number(profile, "marketCap")
    )
    revenue = _number(latest_income, "revenue")
    free_cash_flow = _number(cash_flow, "freeCashFlow")
    pe_ttm = _pick_number(
        quote,
        key_metrics,
        ratios,
        keys=("pe", "peRatioTTM", "peRatio", "priceEarningsRatioTTM", "priceEarningsRatio"),
    )
    ev_ebitda = _pick_number(
        key_metrics,
        ratios,
        keys=("enterpriseValueOverEBITDA", "enterpriseValueMultiple", "evToEbitda"),
    )
    price_to_sales = _pick_number(
        key_metrics,
        ratios,
        keys=("priceToSalesRatio", "priceToSalesRatioTTM"),
    )
    price_to_book = _pick_number(
        key_metrics,
        ratios,
        keys=("pbRatio", "priceToBookRatio", "priceToBookRatioTTM"),
    )
    fcf_yield = _pick_number(key_metrics, ratios, keys=("freeCashFlowYield", "fcfYield"))
    if fcf_yield is None:
        fcf_yield = _divide(free_cash_flow, market_cap)

    revenue_growth = _number(latest_income, "growthRevenue")
    if revenue_growth is None:
        prior_revenue = _number(prior_income, "revenue")
        revenue_growth = _growth(revenue, prior_revenue)

    gross_margin = _pick_number(ratios, latest_income, keys=("grossProfitMargin", "grossMargin"))
    if gross_margin is None:
        gross_margin = _divide(_number(latest_income, "grossProfit"), revenue)
    operating_margin = _pick_number(
        ratios, latest_income, keys=("operatingProfitMargin", "operatingIncomeRatio")
    )
    if operating_margin is None:
        operating_margin = _divide(_number(latest_income, "operatingIncome"), revenue)
    net_margin = _pick_number(ratios, latest_income, keys=("netProfitMargin", "netIncomeRatio"))
    if net_margin is None:
        net_margin = _divide(_number(latest_income, "netIncome"), revenue)
    fcf_margin = _divide(free_cash_flow, revenue)

    financials = SnapshotFinancialMetrics(
        revenue=revenue,
        revenue_growth=revenue_growth,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        net_margin=net_margin,
        eps=_pick_number(latest_income, quote, keys=("eps", "epsdiluted", "epsDiluted")),
        free_cash_flow=free_cash_flow,
        fcf_margin=fcf_margin,
        fcf_yield=fcf_yield,
        roe=_pick_number(ratios, key_metrics, keys=("returnOnEquity", "roe")),
        roic=_pick_number(
            ratios, key_metrics, keys=("returnOnInvestedCapital", "roic", "returnOnCapitalEmployed")
        ),
        debt_to_equity=_pick_number(
            ratios, key_metrics, balance, keys=("debtEquityRatio", "debtToEquity")
        ),
        current_ratio=_pick_number(ratios, key_metrics, balance, keys=("currentRatio",)),
    )
    valuation = SnapshotValuation(
        price=price,
        market_cap=market_cap,
        pe_ttm=pe_ttm,
        forward_pe=_pick_number(quote, key_metrics, ratios, keys=("forwardPE", "forwardPe")),
        ev_ebitda=ev_ebitda,
        price_to_sales=price_to_sales,
        price_to_book=price_to_book,
        fcf_yield=fcf_yield,
        pe_ratio=pe_ttm,
        ev_to_ebitda=ev_ebitda,
    )
    market_data = SnapshotMarketData(
        volume=_number(quote, "volume"),
        avg_volume=_pick_number(quote, profile, keys=("avgVolume", "averageVolume")),
        year_high=_number(quote, "yearHigh"),
        year_low=_number(quote, "yearLow"),
        sector=_text(profile, "sector"),
        industry=_text(profile, "industry"),
    )
    endpoint_errors = {
        endpoint: result.error_type or "fmp_endpoint_unavailable"
        for endpoint, result in results.items()
        if not result.ok
    }
    notes = [
        f"FMP {endpoint} endpoint unavailable ({error_type})."
        for endpoint, error_type in endpoint_errors.items()
    ]
    reliability, label = _data_reliability(
        price=price,
        market_cap=market_cap,
        valuation=valuation,
        financials=financials,
        failure_count=len(endpoint_errors),
        settings=settings,
    )
    return MarketSnapshotData(
        company=SnapshotCompany(
            symbol=symbol,
            name=_text(profile, "companyName") or _text(quote, "name"),
            company_name=_text(profile, "companyName") or _text(quote, "name"),
            marketCap=market_cap,
            currency=_text(profile, "currency") or _text(quote, "currency"),
        ),
        quote=SnapshotQuote(
            price=price,
            market_cap=market_cap,
            volume=market_data.volume,
            avg_volume=market_data.avg_volume,
            year_high=market_data.year_high,
            year_low=market_data.year_low,
        ),
        valuation=valuation,
        metrics=financials,
        financial_metrics=financials,
        market_data=market_data,
        data_reliability=reliability,
        data_reliability_label=label,
        notes=notes,
        error_type=_primary_error_type(endpoint_errors.values()),
        endpoint_errors=endpoint_errors,
    )


def _data_reliability(
    *,
    price: float | None,
    market_cap: float | None,
    valuation: SnapshotValuation,
    financials: SnapshotFinancialMetrics,
    failure_count: int,
    settings: Settings,
) -> tuple[float, str]:
    has_basics = price is not None and market_cap is not None
    has_valuation = any(
        value is not None
        for value in (
            valuation.pe_ttm,
            valuation.ev_ebitda,
            valuation.price_to_sales,
            valuation.fcf_yield,
        )
    )
    has_financials = any(
        value is not None
        for value in (
            financials.revenue,
            financials.revenue_growth,
            financials.eps,
            financials.free_cash_flow,
            financials.roic,
        )
    )
    if has_basics and has_valuation and has_financials:
        reliability = settings.market_snapshot_reliability_financials - min(
            failure_count * 0.02, 0.06
        )
        label = "high" if reliability >= 0.75 else "medium"
    elif has_basics and has_valuation:
        reliability = settings.market_snapshot_reliability_valuation - min(
            failure_count * 0.02, 0.06
        )
        label = "medium"
    elif has_basics:
        reliability = settings.market_snapshot_reliability_basic - min(failure_count * 0.01, 0.03)
        label = "medium_low"
    else:
        reliability = 0.25
        label = "low"
    return round(max(reliability, 0), 2), label


def _primary_error_type(error_types: Any) -> str | None:
    values = set(error_types)
    for error_type in ("fmp_auth_failed_or_plan_limited", "fmp_timeout", "fmp_invalid_response"):
        if error_type in values:
            return error_type
    return "fmp_endpoint_unavailable" if values else None


def _dict_data(result: FMPEndpointResult) -> dict[str, Any]:
    return result.data if isinstance(result.data, dict) else {}


def _list_data(result: FMPEndpointResult) -> list[dict[str, Any]]:
    return result.data if isinstance(result.data, list) else []


def _first(result: FMPEndpointResult) -> dict[str, Any]:
    data = _list_data(result)
    return data[0] if data else _dict_data(result)


def _number(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_number(*sources: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for source in sources:
        for key in keys:
            value = _number(source, key)
            if value is not None:
                return value
    return None


def _text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    return str(value) if value not in (None, "") else None


def _divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 6)


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / abs(previous), 6)
