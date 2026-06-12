from typing import Literal

from pydantic import BaseModel, Field


class MarketSnapshotRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: str = Field(min_length=1, max_length=20)


class SnapshotCompany(BaseModel):
    symbol: str
    name: str | None = None
    company_name: str | None = None
    marketCap: float | None = None
    currency: str | None = None


class SnapshotQuote(BaseModel):
    price: float | None = None
    market_cap: float | None = None
    volume: float | None = None
    avg_volume: float | None = None
    year_high: float | None = None
    year_low: float | None = None


class SnapshotValuation(BaseModel):
    price: float | None = None
    market_cap: float | None = None
    pe_ttm: float | None = None
    forward_pe: float | None = None
    ev_ebitda: float | None = None
    price_to_sales: float | None = None
    price_to_book: float | None = None
    fcf_yield: float | None = None
    enterprise_value: float | None = None
    ev_to_sales: float | None = None
    ev_to_operating_cash_flow: float | None = None
    ev_to_free_cash_flow: float | None = None
    net_debt_to_ebitda: float | None = None
    earnings_yield: float | None = None
    # Compatibility names consumed by the current scoreStock normalizer.
    pe_ratio: float | None = None
    ev_to_ebitda: float | None = None


class SnapshotFinancialMetrics(BaseModel):
    revenue: float | None = None
    revenue_growth: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    eps: float | None = None
    free_cash_flow: float | None = None
    fcf_margin: float | None = None
    fcf_yield: float | None = None
    roe: float | None = None
    roic: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    return_on_assets: float | None = None
    operating_return_on_assets: float | None = None
    return_on_tangible_assets: float | None = None
    invested_capital: float | None = None
    working_capital: float | None = None
    tangible_asset_value: float | None = None
    net_current_asset_value: float | None = None
    free_cash_flow_to_equity: float | None = None
    capex_to_operating_cash_flow: float | None = None
    capex_to_revenue: float | None = None


class SnapshotMarketData(BaseModel):
    volume: float | None = None
    avg_volume: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None


class MarketSnapshotData(BaseModel):
    company: SnapshotCompany
    quote: SnapshotQuote
    valuation: SnapshotValuation
    metrics: SnapshotFinancialMetrics
    financial_metrics: SnapshotFinancialMetrics
    market_data: SnapshotMarketData
    data_reliability: float = Field(ge=0, le=1)
    data_reliability_label: Literal["low", "medium_low", "medium", "high"]
    notes: list[str] = Field(default_factory=list)
    error_type: str | None = None
    endpoint_errors: dict[str, str] = Field(default_factory=dict)


class MarketSnapshotResponse(BaseModel):
    data: MarketSnapshotData
