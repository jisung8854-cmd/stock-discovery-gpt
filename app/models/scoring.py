from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from app.models.common import DataBasis, FinalLabel, Market
from app.models.company import CompanySummary
from app.models.financials import FinancialMetrics, ValuationMetrics


class ScoreModules(BaseModel):
    survival_risk_score: float = Field(ge=0, le=100)
    moat_score: float = Field(ge=0, le=100)
    pricing_power_score: float = Field(ge=0, le=100)
    management_capital_allocation_score: float = Field(ge=0, le=100)
    buffett_fit_score: float = Field(ge=0, le=100)
    price_attractiveness_score: float = Field(ge=0, le=100)
    future_vision_score: float = Field(ge=0, le=100)
    investment_efficiency_score: float = Field(ge=0, le=100)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "survival_risk_score": 88,
                    "moat_score": 86,
                    "pricing_power_score": 82,
                    "management_capital_allocation_score": 80,
                    "buffett_fit_score": 84,
                    "price_attractiveness_score": 74,
                    "future_vision_score": 78,
                    "investment_efficiency_score": 83,
                }
            ]
        }
    )


class CompositeScores(BaseModel):
    total_score: float = Field(ge=0, le=100)
    BQS: float = Field(ge=0, le=100, description="Business quality score")
    PAS: float = Field(ge=0, le=100, description="Price attractiveness score")
    VDS: float = Field(ge=0, le=100, description="Vision durability score")
    EES: float = Field(ge=0, le=100, description="Economic efficiency score")
    modules: ScoreModules


class ScoreValuationMetrics(ValuationMetrics):
    """Score response valuation view with gateway quote context and common aliases."""

    price: float | None = Field(default=None, ge=0)
    market_cap: float | None = Field(default=None, ge=0)
    currency: str | None = None
    per: float | None = None
    forward_per: float | None = None
    ev_ebitda: float | None = None
    fcf_yield: float | None = None


class ScoreResponse(BaseModel):
    company: CompanySummary
    data_basis: DataBasis
    metrics: FinancialMetrics
    valuation: ScoreValuationMetrics
    scores: CompositeScores
    risk_flags: list[str] = Field(default_factory=list)
    hard_fail: bool
    final_label: FinalLabel

    @field_validator("valuation", mode="before")
    @classmethod
    def normalize_valuation(cls, value: object) -> object:
        if isinstance(value, ValuationMetrics) and not isinstance(value, ScoreValuationMetrics):
            return ScoreValuationMetrics(**value.model_dump())
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "company": {
                        "ticker": "AAPL",
                        "market": "NASDAQ",
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "industry": "Consumer Electronics",
                        "market_cap": 3000000000000,
                    },
                    "data_basis": {
                        "source": "fmp",
                        "is_mock": False,
                        "reliability": 0.86,
                        "notes": ["FMP data loaded successfully."],
                    },
                    "metrics": {
                        "revenue_growth": 0.08,
                        "operating_margin": 0.3,
                        "fcf_margin": 0.22,
                        "roic": 0.24,
                        "debt_to_equity": 0.5,
                    },
                    "valuation": {
                        "pe_ratio": 24,
                        "price_to_book": 6,
                        "ev_to_ebitda": 18,
                    },
                    "scores": {
                        "total_score": 78.4,
                        "BQS": 84.2,
                        "PAS": 72.0,
                        "VDS": 81.3,
                        "EES": 82.1,
                        "modules": {
                            "survival_risk_score": 88,
                            "moat_score": 86,
                            "pricing_power_score": 82,
                            "management_capital_allocation_score": 80,
                            "buffett_fit_score": 84,
                            "price_attractiveness_score": 72,
                            "future_vision_score": 78,
                            "investment_efficiency_score": 83,
                        },
                    },
                    "risk_flags": [],
                    "hard_fail": False,
                    "final_label": "strong_candidate",
                }
            ]
        }
    )


class ScreenRequest(BaseModel):
    market: Market = Field(description="Market to screen.")
    min_market_cap: float = Field(default=0, ge=0, description="Minimum market capitalization.")
    min_total_score: float = Field(default=0, ge=0, le=100, description="Minimum total score.")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "market": "NASDAQ",
                    "min_market_cap": 10000000000,
                    "min_total_score": 70,
                    "limit": 10,
                }
            ]
        }
    )


class Candidate(BaseModel):
    ticker: str
    market: Market
    company_name: str
    market_cap: float | None = None
    total_score: float = Field(ge=0, le=100)
    BQS: float = Field(ge=0, le=100)
    PAS: float = Field(ge=0, le=100)
    VDS: float = Field(ge=0, le=100)
    EES: float = Field(ge=0, le=100)
    data_reliability: float = Field(ge=0, le=1)
    final_label: FinalLabel

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ticker": "MSFT",
                    "market": "NASDAQ",
                    "company_name": "Microsoft",
                    "market_cap": 3000000000000,
                    "total_score": 86.2,
                    "BQS": 90.1,
                    "PAS": 74.0,
                    "VDS": 88.4,
                    "EES": 89.0,
                    "data_reliability": 0.5,
                    "final_label": "elite_candidate",
                }
            ]
        }
    )


class ScreenResponse(BaseModel):
    market: Market
    candidates: list[Candidate]
    count: int


class TopCandidatesResponse(RootModel[list[Candidate]]):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                [
                    {
                        "ticker": "MSFT",
                        "market": "NASDAQ",
                        "company_name": "Microsoft",
                        "market_cap": 3000000000000,
                        "total_score": 86.2,
                        "BQS": 90.1,
                        "PAS": 74.0,
                        "VDS": 88.4,
                        "EES": 89.0,
                        "data_reliability": 0.5,
                        "final_label": "elite_candidate",
                    }
                ]
            ]
        }
    )
