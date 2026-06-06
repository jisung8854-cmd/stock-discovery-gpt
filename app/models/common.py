from enum import StrEnum

from pydantic import BaseModel, Field


class Market(StrEnum):
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    AMEX = "AMEX"
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


class FinalLabel(StrEnum):
    ELITE_CANDIDATE = "elite_candidate"
    STRONG_CANDIDATE = "strong_candidate"
    WATCHLIST = "watchlist"
    REJECT = "reject"


class DataBasis(BaseModel):
    source: str = Field(description="Data source used for the response")
    is_mock: bool = Field(description="Whether mock data was used")
    reliability: float = Field(ge=0, le=1, description="Data reliability from 0 to 1")
    notes: list[str] = Field(default_factory=list)
