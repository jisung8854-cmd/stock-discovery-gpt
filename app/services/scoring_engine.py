from dataclasses import dataclass
from statistics import mean

from app.models.common import FinalLabel
from app.models.financials import FinancialMetrics, ValuationMetrics
from app.models.scoring import CompositeScores, ScoreModules

MODULE_WEIGHTS: dict[str, int] = {
    "survival_risk_score": 12,
    "moat_score": 10,
    "pricing_power_score": 6,
    "management_capital_allocation_score": 7,
    "buffett_fit_score": 12,
    "price_attractiveness_score": 40,
    "future_vision_score": 7,
    "investment_efficiency_score": 6,
}

TOTAL_WEIGHT = sum(MODULE_WEIGHTS.values())
LOW_DATA_RELIABILITY_THRESHOLD = 0.5
CRITICAL_DATA_RELIABILITY_THRESHOLD = 0.25

HARD_FAIL_RISK_FLAGS = {
    "audit_opinion_issue",
    "trading_suspension",
    "trading_suspension_related",
    "going_concern_warning",
}


@dataclass(frozen=True)
class ScoringEngine:
    """Deterministic scoring engine for long-term compounder research.

    The engine intentionally scores only quantitative inputs. Qualitative
    interpretation remains the responsibility of the Custom GPT layer.
    """

    def calculate(self, modules: ScoreModules, hard_fail: bool = False) -> CompositeScores:
        weighted_sum = sum(
            getattr(modules, module_name) * weight
            for module_name, weight in MODULE_WEIGHTS.items()
        )
        total_score = round(weighted_sum / TOTAL_WEIGHT, 2)
        bqs = round(
            _weighted_average(
                [
                    (modules.survival_risk_score, MODULE_WEIGHTS["survival_risk_score"]),
                    (modules.moat_score, MODULE_WEIGHTS["moat_score"]),
                    (modules.pricing_power_score, MODULE_WEIGHTS["pricing_power_score"]),
                    (
                        modules.management_capital_allocation_score,
                        MODULE_WEIGHTS["management_capital_allocation_score"],
                    ),
                    (modules.buffett_fit_score, MODULE_WEIGHTS["buffett_fit_score"]),
                ]
            ),
            2,
        )
        pas = round(modules.price_attractiveness_score, 2)
        vds = round(
            _average(
                [modules.future_vision_score, modules.buffett_fit_score, modules.moat_score]
            ),
            2,
        )
        ees = round(
            _average(
                [
                    modules.investment_efficiency_score,
                    modules.management_capital_allocation_score,
                ]
            ),
            2,
        )

        return CompositeScores(
            total_score=total_score,
            BQS=bqs,
            PAS=pas,
            VDS=vds,
            EES=ees,
            modules=modules,
        )

    def calculate_modules(
        self, metrics: FinancialMetrics, valuation: ValuationMetrics
    ) -> ScoreModules:
        """Map normalized financial metrics into the eight weighted modules."""

        fcf_margin = _first_metric(metrics.fcf_margin, metrics.free_cash_flow_margin)
        roic = _first_metric(metrics.roic, metrics.return_on_invested_capital)

        survival_risk_score = _average(
            [
                _score_inverse(metrics.debt_to_equity, excellent=0.2, poor=2.0),
                _score_inverse(metrics.net_debt_to_ebitda, excellent=0.5, poor=4.0),
                _score_positive(metrics.interest_coverage, poor=1.5, excellent=12.0),
                _score_positive(metrics.current_ratio, poor=0.8, excellent=2.0),
                _score_positive(metrics.quick_ratio, poor=0.5, excellent=1.5),
            ]
        )
        moat_score = _average(
            [
                _score_positive(metrics.gross_margin, poor=0.2, excellent=0.6),
                _score_positive(metrics.operating_margin, poor=0.05, excellent=0.3),
                _score_positive(roic, poor=0.05, excellent=0.2),
                _score_positive(metrics.roe, poor=0.08, excellent=0.25),
            ]
        )
        pricing_power_score = _average(
            [
                _score_positive(metrics.gross_margin, poor=0.2, excellent=0.6),
                _score_positive(metrics.net_margin, poor=0.03, excellent=0.2),
                _score_positive(fcf_margin, poor=0.02, excellent=0.25),
            ]
        )
        management_capital_allocation_score = _average(
            [
                _score_positive(roic, poor=0.05, excellent=0.2),
                _score_positive(metrics.roe, poor=0.08, excellent=0.25),
                _score_inverse(metrics.share_count_growth, excellent=-0.02, poor=0.08),
                _score_inverse(metrics.capex_to_revenue, excellent=0.03, poor=0.18),
                _score_positive(
                    metrics.operating_cash_flow_to_net_income,
                    poor=0.8,
                    excellent=1.3,
                ),
            ]
        )
        buffett_fit_score = _average(
            [
                survival_risk_score,
                moat_score,
                pricing_power_score,
                management_capital_allocation_score,
            ]
        )
        price_attractiveness_score = _average(
            [
                _score_positive(metrics.fcf_yield, poor=0.02, excellent=0.08),
                _score_inverse(valuation.pe_ratio, excellent=12, poor=40),
                _score_inverse(valuation.price_to_book, excellent=1, poor=8),
                _score_inverse(valuation.ev_to_ebitda, excellent=8, poor=25),
                _score_positive(valuation.margin_of_safety, poor=0, excellent=0.3),
            ]
        )
        future_vision_score = _average(
            [
                _score_positive(metrics.revenue_growth, poor=-0.05, excellent=0.15),
                _score_positive(fcf_margin, poor=0.02, excellent=0.25),
                _score_positive(roic, poor=0.05, excellent=0.2),
            ]
        )
        investment_efficiency_score = _average(
            [
                _score_positive(roic, poor=0.05, excellent=0.2),
                _score_positive(metrics.roe, poor=0.08, excellent=0.25),
                _score_inverse(metrics.capex_to_revenue, excellent=0.03, poor=0.18),
            ]
        )

        return ScoreModules(
            survival_risk_score=round(survival_risk_score, 2),
            moat_score=round(moat_score, 2),
            pricing_power_score=round(pricing_power_score, 2),
            management_capital_allocation_score=round(
                management_capital_allocation_score, 2
            ),
            buffett_fit_score=round(buffett_fit_score, 2),
            price_attractiveness_score=round(price_attractiveness_score, 2),
            future_vision_score=round(future_vision_score, 2),
            investment_efficiency_score=round(investment_efficiency_score, 2),
        )

    def detect_hard_fail(
        self,
        metrics: FinancialMetrics,
        risk_flags: list[str] | None = None,
        data_reliability: float = 1.0,
    ) -> bool:
        """Detect deterministic hard-fail conditions from metrics and known flags."""

        risk_flag_set = set(risk_flags or [])
        fcf_margin = _first_metric(metrics.fcf_margin, metrics.free_cash_flow_margin)
        roic = _first_metric(metrics.roic, metrics.return_on_invested_capital)
        critical_metrics = [metrics.operating_margin, fcf_margin, roic, metrics.debt_to_equity]

        severe_liquidity_risk = (
            metrics.current_ratio is not None
            and metrics.current_ratio < 0.5
            and (metrics.quick_ratio is None or metrics.quick_ratio < 0.4)
        ) or (
            metrics.interest_coverage is not None
            and metrics.interest_coverage < 0
            and metrics.debt_to_equity is not None
            and metrics.debt_to_equity > 3
        )
        negative_equity = (metrics.total_equity is not None and metrics.total_equity < 0) or (
            metrics.debt_to_equity is not None and metrics.debt_to_equity < 0
        )
        repeated_dilution_with_negative_fcf = (
            metrics.share_count_growth is not None
            and metrics.share_count_growth > 0.1
            and (
                (metrics.free_cash_flow is not None and metrics.free_cash_flow < 0)
                or (fcf_margin is not None and fcf_margin < 0)
            )
        )
        missing_critical_data = data_reliability < CRITICAL_DATA_RELIABILITY_THRESHOLD or all(
            value is None for value in critical_metrics
        )

        return any(
            [
                bool(risk_flag_set & HARD_FAIL_RISK_FLAGS),
                severe_liquidity_risk,
                negative_equity,
                repeated_dilution_with_negative_fcf,
                missing_critical_data,
            ]
        )

    def final_label(
        self,
        total_score: float,
        bqs: float,
        pas: float,
        hard_fail: bool,
        data_reliability: float = 1.0,
        price_attractiveness_score: float | None = None,
    ) -> FinalLabel:
        if hard_fail:
            return FinalLabel.REJECT

        price_score = pas if price_attractiveness_score is None else price_attractiveness_score
        if total_score >= 85 and bqs >= 85 and pas >= 70:
            label = FinalLabel.ELITE_CANDIDATE
        elif total_score >= 70:
            label = FinalLabel.STRONG_CANDIDATE
        elif total_score >= 55:
            label = FinalLabel.WATCHLIST
        else:
            label = FinalLabel.REJECT

        if label == FinalLabel.ELITE_CANDIDATE and price_score < 40:
            label = FinalLabel.STRONG_CANDIDATE
        if data_reliability < LOW_DATA_RELIABILITY_THRESHOLD and label in {
            FinalLabel.ELITE_CANDIDATE,
            FinalLabel.STRONG_CANDIDATE,
        }:
            return FinalLabel.WATCHLIST
        return label


def _weighted_average(weighted_values: list[tuple[float, int]]) -> float:
    numerator = sum(value * weight for value, weight in weighted_values)
    denominator = sum(weight for _, weight in weighted_values)
    return numerator / denominator


def _average(values: list[float | None]) -> float:
    available_values = [value for value in values if value is not None]
    if not available_values:
        return 50
    return mean(available_values)


def _first_metric(*values: float | None) -> float | None:
    return next((value for value in values if value is not None), None)


def _score_positive(value: float | None, poor: float, excellent: float) -> float | None:
    if value is None:
        return None
    if value <= poor:
        return 0
    if value >= excellent:
        return 100
    return round(((value - poor) / (excellent - poor)) * 100, 2)


def _score_inverse(value: float | None, excellent: float, poor: float) -> float | None:
    if value is None:
        return None
    if value <= excellent:
        return 100
    if value >= poor:
        return 0
    return round(((poor - value) / (poor - excellent)) * 100, 2)
