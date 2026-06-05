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
        "Protected Custom GPT Action endpoint. Returns mock MVP candidates filtered by market, "
        "minimum market cap, minimum total score, and result limit."
    ),
    operation_id="screenStocks",
)
def screen(request: ScreenRequest) -> ScreenResponse:
    return ScreenerService().screen(request)


@router.get(
    "/candidates/top",
    response_model=TopCandidatesResponse,
    summary="Get top stock candidates",
    description=(
        "Protected Custom GPT Action endpoint. Returns top-ranked mock candidates, optionally "
        "filtered by market."
    ),
    operation_id="getTopCandidates",
)
def top_candidates(
    market: Market | None = Query(default=None, description="Optional market filter."),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum number of candidates."),
) -> TopCandidatesResponse:
    candidates: list[Candidate] = ScreenerService().top_candidates(market=market, limit=limit)
    return TopCandidatesResponse(candidates)
