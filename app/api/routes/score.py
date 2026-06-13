import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Path

from app.core.config import get_settings
from app.core.security import verify_action_bearer_token
from app.models.common import DataBasis, FinalLabel, Market
from app.models.scoring import ScoreResponse
from app.services.gateway_client import GatewayClient, GatewayResult
from app.services.metrics_calculator import calculate_gateway_metrics
from app.services.normalizer import normalize_gateway_company, resolved_stock_code
from app.services.scoring_engine import ScoringEngine

router = APIRouter(tags=["score"], dependencies=[Depends(verify_action_bearer_token)])
US_MARKETS = {Market.NASDAQ, Market.NYSE, Market.AMEX}
DISCLOSURE_RISK_TERMS = (
    "유상증자",
    "전환사채",
    "최대주주 변경",
    "감사의견",
    "거래정지",
    "going concern",
)


@router.post(
    "/score/{market}/{ticker}",
    response_model=ScoreResponse,
    summary="Score a single stock",
    description=(
        "Protected Custom GPT Action endpoint. Scores one US or Korean listed stock using "
        "normalized stock-data-gateway data with deterministic fallback when data is unavailable. "
        "Does not place trades or generate orders."
    ),
    operation_id="scoreStock",
)
async def score_stock(
    market: Market = Path(description="Listing market for the ticker."),
    ticker: str = Path(
        description="US ticker, Korean company query, or six-digit Korean stock code."
    ),
) -> ScoreResponse:
    settings = get_settings()
    client = GatewayClient(
        base_url=settings.stock_data_gateway_url,
        bearer_token=settings.stock_data_gateway_bearer_token,
    )
    if market in US_MARKETS:
        result = await client.get_market_snapshot(ticker.upper(), market.value)
        return _build_gateway_score(market, ticker, result, provider_flag="fmp_data_unavailable")
    return await _score_korean_stock(client, market, ticker)


async def _score_korean_stock(client: GatewayClient, market: Market, ticker: str) -> ScoreResponse:
    resolve_result: GatewayResult | None = None
    stock_code = ticker
    if not (ticker.isdigit() and len(ticker) == 6):
        resolve_result = await client.resolve_korean_ticker(ticker)
        stock_code = resolved_stock_code(resolve_result.data, ticker)

    company_result, disclosures_result = await asyncio.gather(
        client.get_dart_company_profile(stock_code),
        client.get_dart_disclosures(stock_code),
    )
    results = [company_result, disclosures_result]
    if resolve_result is not None:
        results.append(resolve_result)
    failures = [result for result in results if not result.ok]
    failure_errors = [result.error for result in failures if result.error]
    successful_results = [result for result in results if result.ok]
    company_data = company_result.data if isinstance(company_result.data, dict) else {}
    return _build_gateway_score(
        market,
        stock_code,
        GatewayResult(
            data=company_data,
            error=_aggregate_gateway_error(failure_errors) if not successful_results else None,
        ),
        provider_flag="dart_data_unavailable",
        endpoint_failures=len(failures),
        endpoint_failure_errors=failure_errors,
        extra_flags=_disclosure_risk_flags(disclosures_result.data),
    )


def _build_gateway_score(
    market: Market,
    ticker: str,
    result: GatewayResult,
    provider_flag: str,
    endpoint_failures: int = 0,
    endpoint_failure_errors: list[str] | None = None,
    extra_flags: list[str] | None = None,
) -> ScoreResponse:
    raw = result.data if isinstance(result.data, dict) else {}
    company = normalize_gateway_company(raw, market, ticker)
    metrics, valuation, has_financial_metrics, has_valuation = calculate_gateway_metrics(raw)
    risk_flags = list(extra_flags or [])
    notes: list[str] = []

    if not result.ok:
        risk_flags.extend(["gateway_unavailable", "partial_gateway_data", provider_flag])
        _append_gateway_auth_diagnostic(result.error, risk_flags, notes)
        if result.error not in {"gateway_auth_failed", "gateway_auth_missing"}:
            notes.append(result.error or "stock-data-gateway unavailable")
        reliability = 0.2
    else:
        reliability = _gateway_data_reliability(raw)
        if endpoint_failures:
            risk_flags.extend(["partial_gateway_data", provider_flag])
            notes.append(f"{endpoint_failures} stock-data-gateway endpoint(s) unavailable.")
            for error in endpoint_failure_errors or []:
                _append_gateway_auth_diagnostic(error, risk_flags, notes)
            reliability -= min(endpoint_failures * 0.2, 0.4)
        if not has_financial_metrics:
            risk_flags.extend(["partial_gateway_data", "financial_metrics_missing"])
            notes.append("Detailed financial metrics are unavailable.")
            reliability = min(reliability, 0.45)
        if not has_valuation:
            risk_flags.extend(["partial_gateway_data", "valuation_data_missing"])
            notes.append("Valuation data is unavailable.")
            reliability = min(reliability, 0.45)

    if reliability < 0.5:
        risk_flags.append("low_data_reliability")
    risk_flags = list(dict.fromkeys(risk_flags))
    engine = ScoringEngine()
    modules = engine.calculate_modules(metrics, valuation)
    hard_fail = engine.detect_hard_fail(metrics, risk_flags, reliability)
    if result.ok and not has_financial_metrics:
        hard_fail = False
    scores = engine.calculate(modules, hard_fail=hard_fail)
    final_label = engine.final_label(
        scores.total_score,
        scores.BQS,
        scores.PAS,
        hard_fail,
        data_reliability=reliability,
        price_attractiveness_score=modules.price_attractiveness_score,
    )
    if (
        not hard_fail
        and not has_financial_metrics
        and final_label == FinalLabel.REJECT
        and _has_basic_company_data(company.name, company.ticker, company.price, company.market_cap)
    ):
        final_label = FinalLabel.WATCHLIST

    return ScoreResponse(
        company=company,
        data_basis=DataBasis(
            source="stock-data-gateway",
            is_mock=False,
            reliability=max(round(reliability, 2), 0),
            notes=notes,
        ),
        metrics=metrics,
        valuation=valuation,
        scores=scores,
        risk_flags=risk_flags,
        hard_fail=hard_fail,
        final_label=final_label,
    )


def _gateway_data_reliability(raw: dict[str, Any]) -> float:
    payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    nested = [
        value
        for key in ("metrics", "financial_metrics", "financials", "valuation", "valuation_metrics")
        if isinstance((value := payload.get(key)), dict)
    ]
    available = {
        key
        for source in [payload, *nested]
        for key, value in source.items()
        if value is not None
    }
    valuation = available & {
        "fcf_yield", "earnings_yield", "ev_to_sales", "ev_to_free_cash_flow", "ev_to_ebitda",
    }
    profitability = available & {"roe", "roic", "return_on_assets"}
    liquidity = available & {"current_ratio", "net_debt_to_ebitda"}
    if valuation and profitability and liquidity:
        return 0.7
    if valuation and profitability:
        return 0.65
    if valuation:
        return 0.6
    return 0.45


def _has_basic_company_data(
    name: str, ticker: str, price: float | None, market_cap: float | None
) -> bool:
    return name.upper() != ticker.upper() or price is not None or market_cap is not None


def _disclosure_risk_flags(raw: Any) -> list[str]:
    text = str(raw).lower()
    if any(term.lower() in text for term in DISCLOSURE_RISK_TERMS):
        return ["disclosure_risk_detected"]
    return []


def _aggregate_gateway_error(errors: list[str]) -> str:
    if "gateway_auth_failed" in errors:
        return "gateway_auth_failed"
    if "gateway_auth_missing" in errors:
        return "gateway_auth_missing"
    return "stock-data-gateway unavailable"


def _append_gateway_auth_diagnostic(
    error: str | None, risk_flags: list[str], notes: list[str]
) -> None:
    if error == "gateway_auth_failed":
        risk_flags.append("gateway_auth_failed")
        notes.append("stock-data-gateway authorization failed")
    elif error == "gateway_auth_missing":
        risk_flags.append("gateway_auth_failed")
        notes.append("stock-data-gateway authorization is not configured")
