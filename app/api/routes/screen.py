from fastapi import APIRouter, Depends, Query

from app.core.security import verify_action_bearer_token
from app.models.common import Market
from app.models.scoring import Candidate, ScreenRequest, ScreenResponse, TopCandidatesResponse
from app.services.screener import ScreenerService

router = APIRouter(tags=["screen"], dependencies=[Depends(verify_action_bearer_token)])


@router.post(
    "/screen",
    response_model=ScreenResponse,
    summary="Screen stock candidates",
    description=(
        "Protected Custom GPT Action endpoint. Returns candidates filtered by market, minimum "
        "market cap, minimum total score, and result limit. Market cap is USD for NASDAQ/NYSE/"
        "AMEX and KRW for KOSPI/KOSDAQ; candidates with unavailable market cap remain eligible "
        "when min_market_cap is 0."
    ),
    operation_id="screenStocks",
)
def screen(request: ScreenRequest) -> ScreenResponse:
    service = ScreenerService()
    try:
        return service.screen(request)
    except Exception:
        return service.fallback_screen(request, gateway_unavailable=True)


@router.get(
    "/candidates/top",
    response_model=TopCandidatesResponse,
    summary="Get top stock candidates",
    description=(
        "Protected Custom GPT Action endpoint. Returns top-ranked candidates with source, "
        "reliability, market-cap unit, and risk metadata, optionally filtered by market."
    ),
    operation_id="getTopCandidates",
)
def top_candidates(
    market: Market | None = Query(default=None, description="Optional market filter."),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum number of candidates."),
) -> TopCandidatesResponse:
    service = ScreenerService()
    try:
        candidates: list[Candidate] = service.top_candidates(market=market, limit=limit)
    except Exception:
        candidates = service.fallback_candidates(
            market=market,
            limit=limit,
            gateway_unavailable=True,
        )
    return TopCandidatesResponse(candidates)
