from app.models.common import FinalLabel
from app.models.financials import FinancialMetrics, ValuationMetrics
from app.models.scoring import ScoreModules
from app.services.scoring_engine import MODULE_WEIGHTS, TOTAL_WEIGHT, ScoringEngine


def test_total_score_is_weighted_sum() -> None:
    modules = ScoreModules(
        survival_risk_score=90,
        moat_score=80,
        pricing_power_score=70,
        management_capital_allocation_score=60,
        buffett_fit_score=85,
        price_attractiveness_score=75,
        future_vision_score=65,
        investment_efficiency_score=95,
    )
    expected = round(
        sum(getattr(modules, name) * weight for name, weight in MODULE_WEIGHTS.items())
        / TOTAL_WEIGHT,
        2,
    )

    scores = ScoringEngine().calculate(modules)

    assert scores.total_score == expected


def test_final_label_elite_candidate() -> None:
    label = ScoringEngine().final_label(total_score=88, bqs=86, pas=72, hard_fail=False)

    assert label == FinalLabel.ELITE_CANDIDATE


def test_final_label_strong_candidate() -> None:
    label = ScoringEngine().final_label(total_score=75, bqs=68, pas=62, hard_fail=False)

    assert label == FinalLabel.STRONG_CANDIDATE


def test_final_label_watchlist() -> None:
    label = ScoringEngine().final_label(total_score=60, bqs=58, pas=55, hard_fail=False)

    assert label == FinalLabel.WATCHLIST


def test_final_label_rejects_hard_fail() -> None:
    label = ScoringEngine().final_label(total_score=90, bqs=90, pas=90, hard_fail=True)

    assert label == FinalLabel.REJECT


def _label_for(
    metrics: FinancialMetrics, valuation: ValuationMetrics, reliability: float = 1.0
) -> FinalLabel:
    engine = ScoringEngine()
    modules = engine.calculate_modules(metrics, valuation)
    hard_fail = engine.detect_hard_fail(metrics, data_reliability=reliability)
    scores = engine.calculate(modules, hard_fail=hard_fail)
    return engine.final_label(
        scores.total_score,
        scores.BQS,
        scores.PAS,
        hard_fail,
        data_reliability=reliability,
        price_attractiveness_score=modules.price_attractiveness_score,
    )


def _high_quality_metrics() -> FinancialMetrics:
    return FinancialMetrics(
        revenue_growth=0.16,
        gross_margin=0.65,
        operating_margin=0.35,
        net_margin=0.24,
        free_cash_flow=12_000_000_000,
        fcf_margin=0.24,
        free_cash_flow_margin=0.24,
        fcf_yield=0.07,
        roic=0.24,
        return_on_invested_capital=0.24,
        roe=0.3,
        debt_to_equity=0.1,
        net_debt_to_ebitda=0.2,
        interest_coverage=20,
        share_count_growth=-0.03,
        capex_to_revenue=0.03,
        operating_cash_flow_to_net_income=1.2,
        current_ratio=2.4,
        quick_ratio=1.7,
        total_equity=60_000_000_000,
    )


def test_high_quality_company_with_fair_valuation_is_elite_candidate() -> None:
    label = _label_for(
        _high_quality_metrics(),
        ValuationMetrics(
            pe_ratio=16,
            price_to_book=2,
            ev_to_ebitda=10,
            margin_of_safety=0.25,
        ),
    )

    assert label == FinalLabel.ELITE_CANDIDATE


def test_high_quality_company_with_expensive_valuation_is_not_elite() -> None:
    label = _label_for(
        _high_quality_metrics(),
        ValuationMetrics(
            pe_ratio=75,
            price_to_book=14,
            ev_to_ebitda=35,
            margin_of_safety=-0.1,
        ),
    )

    assert label in {FinalLabel.WATCHLIST, FinalLabel.STRONG_CANDIDATE}
    assert label != FinalLabel.ELITE_CANDIDATE


def test_weak_company_with_cheap_valuation_is_reject_or_watchlist() -> None:
    label = _label_for(
        FinancialMetrics(
            revenue_growth=-0.1,
            gross_margin=0.15,
            operating_margin=0.01,
            net_margin=-0.02,
            free_cash_flow=-1_000_000_000,
            fcf_margin=-0.03,
            free_cash_flow_margin=-0.03,
            fcf_yield=0.12,
            roic=0.01,
            return_on_invested_capital=0.01,
            roe=-0.05,
            debt_to_equity=1.8,
            net_debt_to_ebitda=3.5,
            interest_coverage=1.2,
            share_count_growth=0.05,
            capex_to_revenue=0.2,
            operating_cash_flow_to_net_income=0.4,
            current_ratio=0.9,
            quick_ratio=0.6,
            total_equity=10_000_000_000,
        ),
        ValuationMetrics(
            pe_ratio=8,
            price_to_book=0.8,
            ev_to_ebitda=6,
            margin_of_safety=0.4,
        ),
    )

    assert label in {FinalLabel.REJECT, FinalLabel.WATCHLIST}


def test_hard_fail_company_is_reject() -> None:
    engine = ScoringEngine()
    metrics = _high_quality_metrics()
    valuation = ValuationMetrics(pe_ratio=16, price_to_book=2, ev_to_ebitda=10)
    modules = engine.calculate_modules(metrics, valuation)
    hard_fail = engine.detect_hard_fail(metrics, risk_flags=["audit_opinion_issue"])
    scores = engine.calculate(modules, hard_fail=hard_fail)

    label = engine.final_label(scores.total_score, scores.BQS, scores.PAS, hard_fail)

    assert hard_fail is True
    assert label == FinalLabel.REJECT


def test_low_data_reliability_cannot_be_elite() -> None:
    label = _label_for(
        _high_quality_metrics(),
        ValuationMetrics(
            pe_ratio=16,
            price_to_book=2,
            ev_to_ebitda=10,
            margin_of_safety=0.25,
        ),
        reliability=0.4,
    )

    assert label == FinalLabel.WATCHLIST


def test_detailed_snapshot_metrics_change_each_composite_score() -> None:
    engine = ScoringEngine()
    modules = engine.calculate_modules(
        FinancialMetrics(
            fcf_yield=0.06,
            roic=0.22,
            roe=0.28,
            current_ratio=1.8,
            net_debt_to_ebitda=0.4,
            capex_to_revenue=0.05,
        ),
        ValuationMetrics(ev_to_ebitda=12),
    )
    scores = engine.calculate(modules)

    assert scores.total_score != 50
    assert all(getattr(scores, key) != 50 for key in ("BQS", "PAS", "VDS", "EES"))
