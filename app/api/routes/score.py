import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Path

from app.core.config import get_settings
from app.core.security import verify_action_bearer_token
from app.models.common import DataBasis, FinalLabel, Market
from app.models.company import CompanySummary
from app.models.financials import FinancialMetrics
from app.models.scoring import ScoreResponse, ScoreValuationMetrics
from app.services.gateway_client import GatewayClient, GatewayResult
from app.services.metrics_calculator import calculate_gateway_metrics
from app.services.normalizer import gateway_value, normalize_gateway_company, resolved_stock_code
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
    client = GatewayClient(settings.stock_data_gateway_url)
    if market in US_MARKETS:
        result = await client.get_market_snapshot(ticker.upper(), market.value)
        return _build_gateway_score(market, ticker, result, provider_flag="fmp_data_unavailable")
    return await _score_korean_stock(client, market, ticker)


async def _score_korean_stock(client: GatewayClient, market: Market, ticker: str) -> ScoreResponse:
    resolve_result = GatewayResult(data={"stock_code": ticker})
    stock_code = ticker
    if not (ticker.isdigit() and len(ticker) == 6):
        resolve_result = await client.resolve_korean_ticker(ticker)
        stock_code = resolved_stock_code(resolve_result.data, ticker)

    company_result, disclosures_result = await asyncio.gather(
        client.get_dart_company_profile(stock_code),
        client.get_dart_disclosures(stock_code),
    )
    successful_data = company_result.data if isinstance(company_result.data, dict) else {}
    results = (resolve_result, company_result, disclosures_result)
    failures = [result for result in results if not result.ok]
    extra_flags, critical_disclosure = _disclosure_analysis(disclosures_result.data)
    return _build_gateway_score(
        market,
        stock_code,
        GatewayResult(data=successful_data, error=company_result.error),
        provider_flag="dart_data_unavailable",
        endpoint_failures=len(failures),
        extra_flags=extra_flags,
        critical_disclosure=critical_disclosure,
    )


def _build_gateway_score(
    market: Market,
    ticker: str,
    result: GatewayResult,
    provider_flag: str,
    endpoint_failures: int = 0,
    extra_flags: list[str] | None = None,
    critical_disclosure: bool = False,
) -> ScoreResponse:
    raw = result.data if isinstance(result.data, dict) else {}
    company = normalize_gateway_company(raw, market, ticker)
    metrics, base_valuation, has_financial_metrics, has_valuation_metrics = (
        calculate_gateway_metrics(raw)
    )
    valuation = ScoreValuationMetrics(
        **base_valuation.model_dump(),
        price=company.price,
        market_cap=company.market_cap,
        currency=company.currency,
        per=base_valuation.pe_ratio,
        forward_per=base_valuation.forward_pe,
        ev_ebitda=base_valuation.ev_to_ebitda,
        fcf_yield=metrics.fcf_yield,
    )
    risk_flags = list(extra_flags or [])
    notes: list[str] = []

    if not result.ok:
        reliability = 0.1
        risk_flags.extend(
            ["gateway_unavailable", "partial_gateway_data", provider_flag, "low_data_reliability"]
        )
        notes.append(result.error or "stock-data-gateway unavailable")
    else:
        reliability = _gateway_reliability(company, has_financial_metrics, has_valuation_metrics)
        if endpoint_failures:
            risk_flags.extend(["partial_gateway_data", provider_flag])
            notes.append(f"{endpoint_failures} stock-data-gateway endpoint(s) unavailable.")
            reliability = max(reliability - min(endpoint_failures * 0.1, 0.3), 0.1)

    if _valuation_data_missing(valuation):
        risk_flags.extend(["partial_gateway_data", "valuation_data_missing"])
        notes.append("Some valuation fields are unavailable.")
    if _financial_metrics_missing(metrics):
        risk_flags.extend(["partial_gateway_data", "financial_metrics_missing"])
        notes.append("Some financial metric fields are unavailable.")
    if reliability < 0.5:
        risk_flags.append("low_data_reliability")
        notes.append("Gateway data reliability is low.")

    risk_flags = list(dict.fromkeys(risk_flags))
    notes = list(dict.fromkeys(notes))
    engine = ScoringEngine()
    modules = engine.calculate_modules(metrics, valuation)
    hard_fail = critical_disclosure or engine.detect_hard_fail(metrics, risk_flags, reliability)
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
        final_label == FinalLabel.REJECT
        and not hard_fail
        and reliability >= 0.5
        and company.price is not None
        and company.name.upper() != company.ticker.upper()
    ):
        final_label = FinalLabel.WATCHLIST

    return ScoreResponse(
        company=company,
        data_basis=DataBasis(
            source=str(gateway_value(raw, "source") or "stock-data-gateway"),
            is_mock=not result.ok,
            reliability=round(reliability, 2),
            notes=notes,
        ),
        metrics=metrics,
        valuation=valuation,
        scores=scores,
        risk_flags=risk_flags,
        hard_fail=hard_fail,
        final_label=final_label,
    )


def _gateway_reliability(
    company: CompanySummary, has_financials: bool, has_valuation: bool
) -> float:
    core_values = [
        company.name.upper() != company.ticker.upper(),
        company.price is not None,
        company.market_cap is not None,
    ]
    core_count = sum(core_values)
    reliability = {0: 0.2, 1: 0.45, 2: 0.75, 3: 0.9}[core_count]
    if (has_financials or has_valuation) and reliability < 0.6:
        reliability = 0.6
    return reliability


def _valuation_data_missing(valuation: ScoreValuationMetrics) -> bool:
    values = (
        valuation.price,
        valuation.market_cap,
        valuation.currency,
        valuation.per,
        valuation.forward_per,
        valuation.ev_ebitda,
        valuation.fcf_yield,
    )
    return any(value is None for value in values)


def _financial_metrics_missing(metrics: FinancialMetrics) -> bool:
    fields = (
        "revenue_growth",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "free_cash_flow",
        "fcf_margin",
        "roe",
        "roic",
        "debt_to_equity",
        "current_ratio",
    )
    return any(getattr(metrics, field) is None for field in fields)


def _disclosure_analysis(raw: Any) -> tuple[list[str], bool]:
    text = str(raw).lower()
    detected = any(term.lower() in text for term in DISCLOSURE_RISK_TERMS)
    critical_terms = ("감사의견", "거래정지", "going concern")
    critical = any(term.lower() in text for term in critical_terms)
    return (["disclosure_risk_detected"] if detected else []), critical
