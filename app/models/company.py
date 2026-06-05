from pydantic import BaseModel, Field

from app.models.common import Market


class CompanySummary(BaseModel):
    ticker: str
    market: Market
    name: str
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = Field(default=None, ge=0)
