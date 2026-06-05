from typing import Any

from app.models.financials import FinancialMetrics, ValuationMetrics


def build_mock_financial_metrics() -> FinancialMetrics:
    return FinancialMetrics(
        revenue_growth=0.12,
        gross_margin=0.55,
        operating_margin=0.24,
        net_margin=0.18,
        free_cash_flow=9_000_000_000,
        fcf_margin=0.18,
        free_cash_flow_margin=0.18,
        fcf_yield=0.045,
        roic=0.16,
        return_on_invested_capital=0.16,
        roe=0.22,
        debt_to_equity=0.35,
        net_debt_to_ebitda=0.6,
        interest_coverage=14.0,
        share_count_growth=-0.01,
        capex_to_revenue=0.04,
        operating_cash_flow_to_net_income=1.15,
        current_ratio=1.8,
        quick_ratio=1.3,
        total_equity=80_000_000_000,
    )


def build_mock_valuation_metrics() -> ValuationMetrics:
    return ValuationMetrics(
        pe_ratio=22.5,
        forward_pe=19.8,
        price_to_book=4.2,
        ev_to_ebitda=14.1,
        margin_of_safety=0.18,
    )


def build_empty_valuation_metrics() -> ValuationMetrics:
    return ValuationMetrics()


def calculate_fmp_financial_metrics(
    income_statements: list[dict[str, Any]],
    balance_sheets: list[dict[str, Any]],
    cash_flow_statements: list[dict[str, Any]],
    ratios: list[dict[str, Any]],
    key_metrics: list[dict[str, Any]],
    quote: dict[str, Any] | None = None,
) -> FinancialMetrics:
    latest_income = _first(income_statements)
    previous_income = _nth(income_statements, 1)
    latest_balance = _first(balance_sheets)
    latest_cash_flow = _first(cash_flow_statements)
    previous_key_metrics = _nth(key_metrics, 1)
    latest_ratios = _first(ratios)
    latest_key_metrics = _first(key_metrics)
    quote = quote or {}

    latest_revenue = _number(latest_income, "revenue")
    previous_revenue = _number(previous_income, "revenue")
    gross_profit = _number(latest_income, "grossProfit")
    operating_income = _number(latest_income, "operatingIncome")
    net_income = _number(latest_income, "netIncome")
    ebitda = _first_available_number(latest_income, latest_key_metrics, keys=("ebitda", "EBITDA"))
    interest_expense = _number(latest_income, "interestExpense")

    operating_cash_flow = _number(latest_cash_flow, "operatingCashFlow")
    capital_expenditure = _number(latest_cash_flow, "capitalExpenditure")
    free_cash_flow = _number(latest_cash_flow, "freeCashFlow")
    if (
        free_cash_flow is None
        and operating_cash_flow is not None
        and capital_expenditure is not None
    ):
        free_cash_flow = operating_cash_flow + capital_expenditure

    total_debt = _number(latest_balance, "totalDebt")
    if total_debt is None:
        short_term_debt = _number(latest_balance, "shortTermDebt") or 0
        long_term_debt = _number(latest_balance, "longTermDebt") or 0
        total_debt = short_term_debt + long_term_debt
    cash_and_equivalents = _first_available_number(
        latest_balance,
        keys=("cashAndShortTermInvestments", "cashAndCashEquivalents"),
    )
    total_equity = _number(latest_balance, "totalStockholdersEquity")
    current_assets = _number(latest_balance, "totalCurrentAssets")
    current_liabilities = _number(latest_balance, "totalCurrentLiabilities")
    inventory = _number(latest_balance, "inventory") or 0

    current_shares = _first_available_number(
        latest_income,
        latest_key_metrics,
        quote,
        keys=("weightedAverageShsOut", "weightedAverageShsOutDil", "sharesOutstanding"),
    )
    previous_shares = _first_available_number(
        previous_income,
        previous_key_metrics,
        keys=("weightedAverageShsOut", "weightedAverageShsOutDil"),
    )
    market_cap = _first_available_number(quote, latest_key_metrics, keys=("marketCap", "mktCap"))
    roic = _first_available_number(
        latest_ratios,
        latest_key_metrics,
        keys=("returnOnInvestedCapital", "roic"),
    )

    fcf_margin = _safe_divide(free_cash_flow, latest_revenue)
    roe = _first_available_number(latest_ratios, latest_key_metrics, keys=("returnOnEquity", "roe"))
    if roe is None:
        roe = _safe_divide(net_income, total_equity)

    return FinancialMetrics(
        revenue_growth=_growth(latest_revenue, previous_revenue),
        gross_margin=_safe_divide(gross_profit, latest_revenue),
        operating_margin=_safe_divide(operating_income, latest_revenue),
        net_margin=_safe_divide(net_income, latest_revenue),
        free_cash_flow=free_cash_flow,
        fcf_margin=fcf_margin,
        free_cash_flow_margin=fcf_margin,
        fcf_yield=_safe_divide(free_cash_flow, market_cap),
        roic=roic,
        return_on_invested_capital=roic,
        roe=roe,
        debt_to_equity=_safe_divide(total_debt, total_equity),
        net_debt_to_ebitda=_safe_divide(
            None if total_debt is None else total_debt - (cash_and_equivalents or 0),
            ebitda,
        ),
        interest_coverage=_safe_divide(operating_income, _abs_or_none(interest_expense)),
        share_count_growth=_growth(current_shares, previous_shares),
        capex_to_revenue=_safe_divide(_abs_or_none(capital_expenditure), latest_revenue),
        operating_cash_flow_to_net_income=_safe_divide(operating_cash_flow, net_income),
        current_ratio=_first_available_number(latest_ratios, keys=("currentRatio",))
        or _safe_divide(current_assets, current_liabilities),
        quick_ratio=_first_available_number(latest_ratios, keys=("quickRatio",))
        or _safe_divide(
            None if current_assets is None else current_assets - inventory,
            current_liabilities,
        ),
        total_equity=total_equity,
    )


def calculate_fmp_valuation_metrics(
    key_metrics: list[dict[str, Any]],
    ratios: list[dict[str, Any]],
    quote: dict[str, Any] | None,
) -> ValuationMetrics:
    latest_key_metrics = _first(key_metrics)
    latest_ratios = _first(ratios)
    quote = quote or {}

    return ValuationMetrics(
        pe_ratio=_first_available_number(
            latest_key_metrics,
            latest_ratios,
            quote,
            keys=("peRatio", "priceEarningsRatio", "pe"),
        ),
        forward_pe=None,
        price_to_book=_first_available_number(
            latest_key_metrics,
            latest_ratios,
            keys=("pbRatio", "priceToBookRatio"),
        ),
        ev_to_ebitda=_first_available_number(
            latest_key_metrics,
            latest_ratios,
            keys=("enterpriseValueOverEBITDA", "evToEbitda"),
        ),
        margin_of_safety=None,
    )


def calculate_dart_financial_metrics(financial_rows: list[dict[str, Any]]) -> FinancialMetrics:
    latest_revenue = _dart_account_number(
        financial_rows, ("매출액", "수익(매출액)", "영업수익")
    )
    previous_revenue = _dart_account_number(
        financial_rows, ("매출액", "수익(매출액)", "영업수익"), amount_key="frmtrm_amount"
    )
    gross_profit = _dart_account_number(financial_rows, ("매출총이익",))
    operating_income = _dart_account_number(financial_rows, ("영업이익",))
    net_income = _dart_account_number(financial_rows, ("당기순이익", "당기순이익(손실)"))
    total_debt = _dart_account_number(financial_rows, ("부채총계",))
    total_equity = _dart_account_number(financial_rows, ("자본총계",))
    total_assets = _dart_account_number(financial_rows, ("자산총계",))
    current_assets = _dart_account_number(financial_rows, ("유동자산",))
    current_liabilities = _dart_account_number(financial_rows, ("유동부채",))

    net_margin = _safe_divide(net_income, latest_revenue)
    roic = _safe_divide(net_income, total_assets)
    return FinancialMetrics(
        revenue_growth=_growth(latest_revenue, previous_revenue),
        gross_margin=_safe_divide(gross_profit, latest_revenue),
        operating_margin=_safe_divide(operating_income, latest_revenue),
        net_margin=net_margin,
        free_cash_flow=net_income,
        fcf_margin=net_margin,
        free_cash_flow_margin=net_margin,
        roic=roic,
        return_on_invested_capital=roic,
        roe=_safe_divide(net_income, total_equity),
        debt_to_equity=_safe_divide(total_debt, total_equity),
        current_ratio=_safe_divide(current_assets, current_liabilities),
        total_equity=total_equity,
    )


def _first(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[0] if items else {}


def _nth(items: list[dict[str, Any]], index: int) -> dict[str, Any]:
    return items[index] if len(items) > index else {}


def _number(source: dict[str, Any], key: str) -> float | None:
    value = source.get(key)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _first_available_number(*sources: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for source in sources:
        for key in keys:
            value = _number(source, key)
            if value is not None:
                return value
    return None


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 4)


def _growth(latest: float | None, previous: float | None) -> float | None:
    if latest is None or previous in (None, 0):
        return None
    return round((latest - previous) / abs(previous), 4)


def _abs_or_none(value: float | None) -> float | None:
    return abs(value) if value is not None else None


def _dart_account_number(
    rows: list[dict[str, Any]],
    account_names: tuple[str, ...],
    amount_key: str = "thstrm_amount",
) -> float | None:
    for row in rows:
        account_name = str(row.get("account_nm") or "").replace(" ", "")
        normalized_names = tuple(name.replace(" ", "") for name in account_names)
        if account_name in normalized_names:
            return _parse_dart_amount(row.get(amount_key))
    return None


def _parse_dart_amount(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return -parsed if negative else parsed
