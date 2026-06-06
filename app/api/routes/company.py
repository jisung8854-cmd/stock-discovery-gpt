from fastapi import APIRouter, Depends

from app.core.security import verify_action_bearer_token
from app.models.common import Market
from app.models.company import CompanySummary
from app.services.normalizer import normalize_company

router = APIRouter(tags=["company"], dependencies=[Depends(verify_action_bearer_token)])


@router.get("/company/{market}/{ticker}", response_model=CompanySummary)
def company_profile(market: Market, ticker: str) -> CompanySummary:
    return normalize_company({}, market, ticker)
