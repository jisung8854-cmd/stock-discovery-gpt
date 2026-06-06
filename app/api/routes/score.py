from fastapi import APIRouter, Depends, Path

from app.core.security import verify_action_bearer_token
from app.models.common import Market
from app.models.scoring import ScoreResponse
from app.services.screener import ScreenerService

router = APIRouter(tags=["score"], dependencies=[Depends(verify_action_bearer_token)])


@router.post(
    "/score/{market}/{ticker}",
    response_model=ScoreResponse,
    summary="Score a single stock",
    description=(
        "Protected Custom GPT Action endpoint. Scores one US or Korean listed stock using "
        "FMP/DART data when configured, with deterministic mock fallback when data providers "
        "are unavailable. Does not place trades or generate orders."
    ),
    operation_id="scoreStock",
)
async def score_stock(
    market: Market = Path(description="Listing market for the ticker."),
    ticker: str = Path(
        description="US ticker or six-digit Korean stock code, such as AAPL or 005930."
    ),
) -> ScoreResponse:
    return await ScreenerService().score_stock(market, ticker)
