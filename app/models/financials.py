from pydantic import BaseModel


class FinancialMetrics(BaseModel):
    revenue_growth: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    free_cash_flow: float | None = None
    fcf_margin: float | None = None
    fcf_yield: float | None = None
    roic: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    share_count_growth: float | None = None
    capex_to_revenue: float | None = None
    operating_cash_flow_to_net_income: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    total_equity: float | None = None

    # Backward-compatible aliases used by earlier service code and clients.
    free_cash_flow_margin: float | None = None
    return_on_invested_capital: float | None = None


class ValuationMetrics(BaseModel):
    pe_ratio: float | None = None
    forward_pe: float | None = None
    price_to_book: float | None = None
    ev_to_ebitda: float | None = None
    margin_of_safety: float | None = None
