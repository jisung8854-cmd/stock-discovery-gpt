import asyncio
from datetime import date
from typing import Any

from app.core.config import Settings, get_settings
from app.models.common import DataBasis, Market
from app.models.company import CompanySummary
from app.models.financials import FinancialMetrics, ValuationMetrics
from app.models.scoring import Candidate, ScoreModules, ScoreResponse, ScreenRequest, ScreenResponse
from app.services.dart_client import DARTClient, DARTEndpointResult
from app.services.fmp_client import FMPClient, FMPEndpointResult
from app.services.metrics_calculator import (
    build_empty_valuation_metrics,
    build_mock_financial_metrics,
    build_mock_valuation_metrics,
    calculate_dart_financial_metrics,
    calculate_fmp_financial_metrics,
    calculate_fmp_valuation_metrics,
)
from app.services.normalizer import normalize_company, normalize_dart_company, normalize_fmp_company
from app.services.scoring_engine import ScoringEngine

US_MARKETS = {Market.NASDAQ, Market.NYSE, Market.AMEX}
KOREAN_MARKETS = {Market.KOSPI, Market.KOSDAQ}
DART_ANNUAL_REPORT_CODE = "11011"



class ScreenerService:
    def __init__(
        self,
        scoring_engine: ScoringEngine | None = None,
        settings: Settings | None = None,
        fmp_client: FMPClient | None = None,
        dart_client: DARTClient | None = None,
    ) -> None:
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.settings = settings or get_settings()
        self.fmp_client = fmp_client or FMPClient(api_key=self.settings.fmp_api_key)
        self.dart_client = dart_client or DARTClient(api_key=self.settings.dart_api_key)

    async def score_stock(self, market: Market, ticker: str) -> ScoreResponse:
        if market in US_MARKETS and self.settings.fmp_api_key:
            return await self._score_us_stock_with_fmp(market, ticker)
        if market in KOREAN_MARKETS and self.settings.dart_api_key:
            return await self._score_korean_stock_with_dart(market, ticker)
        return self._score_stock_with_mock(market, ticker)

    def _score_stock_with_mock(self, market: Market, ticker: str) -> ScoreResponse:
        company = normalize_company({}, market, ticker)
        modules = ScoreModules(
            survival_risk_score=82,
            moat_score=78,
            pricing_power_score=76,
            management_capital_allocation_score=74,
            buffett_fit_score=80,
            price_attractiveness_score=72,
            future_vision_score=79,
            investment_efficiency_score=75,
        )
        hard_fail = False
        scores = self.scoring_engine.calculate(modules, hard_fail=hard_fail)
        final_label = self.scoring_engine.final_label(
            scores.total_score,
            scores.BQS,
            scores.PAS,
            hard_fail,
        )
        return ScoreResponse(
            company=company,
            data_basis=DataBasis(
                source="mock",
                is_mock=True,
                reliability=0.5,
                notes=["API key is missing or selected market is not data-provider-backed yet."],
            ),
            metrics=build_mock_financial_metrics(),
            valuation=build_mock_valuation_metrics(),
            scores=scores,
            risk_flags=[],
            hard_fail=hard_fail,
            final_label=final_label,
        )

    async def _score_us_stock_with_fmp(self, market: Market, ticker: str) -> ScoreResponse:
        (
            profile_result,
            income_result,
            balance_result,
            cash_flow_result,
            key_metrics_result,
            ratios_result,
            quote_result,
        ) = await asyncio.gather(
            self.fmp_client.get_company_profile(ticker),
            self.fmp_client.get_income_statement(ticker),
            self.fmp_client.get_balance_sheet(ticker),
            self.fmp_client.get_cash_flow_statement(ticker),
            self.fmp_client.get_key_metrics(ticker),
            self.fmp_client.get_ratios(ticker),
            self.fmp_client.get_quote(ticker),
        )

        results = [
            profile_result,
            income_result,
            balance_result,
            cash_flow_result,
            key_metrics_result,
            ratios_result,
            quote_result,
        ]
        notes = [result.error for result in results if result.error]
        reliability = self._data_reliability(results)

        profile = _dict_data(profile_result)
        quote = _dict_data(quote_result)
        income_statements = _list_data(income_result)
        balance_sheets = _list_data(balance_result)
        cash_flow_statements = _list_data(cash_flow_result)
        key_metrics = _list_data(key_metrics_result)
        ratios = _list_data(ratios_result)

        company = normalize_fmp_company(profile, quote, market, ticker)
        metrics = calculate_fmp_financial_metrics(
            income_statements,
            balance_sheets,
            cash_flow_statements,
            ratios,
            key_metrics,
            quote,
        )
        valuation = calculate_fmp_valuation_metrics(key_metrics, ratios, quote)
        modules = self._score_modules_from_fmp(metrics, valuation, reliability)
        risk_flags = self._risk_flags(metrics, valuation, reliability)
        hard_fail = self.scoring_engine.detect_hard_fail(metrics, risk_flags, reliability)
        scores = self.scoring_engine.calculate(modules, hard_fail=hard_fail)
        final_label = self.scoring_engine.final_label(
            scores.total_score,
            scores.BQS,
            scores.PAS,
            hard_fail,
            data_reliability=reliability,
            price_attractiveness_score=modules.price_attractiveness_score,
        )

        return ScoreResponse(
            company=company,
            data_basis=DataBasis(
                source="fmp",
                is_mock=False,
                reliability=reliability,
                notes=notes or ["FMP data loaded successfully."],
            ),
            metrics=metrics,
            valuation=valuation,
            scores=scores,
            risk_flags=risk_flags,
            hard_fail=hard_fail,
            final_label=final_label,
        )


    async def _score_korean_stock_with_dart(self, market: Market, ticker: str) -> ScoreResponse:
        normalized_ticker = ticker.zfill(6)
        statement_year = date.today().year - 1
        mapping_result = await self.dart_client.get_corp_code_mapping()
        overview_result, financial_result, filings_result = await asyncio.gather(
            self.dart_client.get_company_overview(normalized_ticker),
            self.dart_client.get_financial_statement(
                normalized_ticker, statement_year, DART_ANNUAL_REPORT_CODE
            ),
            self.dart_client.get_recent_filings(normalized_ticker),
        )

        results = [mapping_result, overview_result, financial_result, filings_result]
        notes = [result.error for result in results if result.error]
        reliability = self._data_reliability(results)

        overview = _dict_data(overview_result)
        financial_rows = _list_data(financial_result)
        filings = _list_data(filings_result)

        company = normalize_dart_company(overview, market, normalized_ticker)
        metrics = calculate_dart_financial_metrics(financial_rows)
        valuation = build_empty_valuation_metrics()
        modules = self._score_modules_from_fmp(metrics, valuation, reliability)
        dart_risk_flags = self._dart_filing_risk_flags(filings)
        risk_flags = self._risk_flags(metrics, valuation, reliability, provider="dart")
        risk_flags.extend(flag for flag in dart_risk_flags if flag not in risk_flags)
        hard_fail = self.scoring_engine.detect_hard_fail(metrics, risk_flags, reliability)
        scores = self.scoring_engine.calculate(modules, hard_fail=hard_fail)
        final_label = self.scoring_engine.final_label(
            scores.total_score,
            scores.BQS,
            scores.PAS,
            hard_fail,
            data_reliability=reliability,
            price_attractiveness_score=modules.price_attractiveness_score,
        )

        return ScoreResponse(
            company=company,
            data_basis=DataBasis(
                source="dart",
                is_mock=False,
                reliability=reliability,
                notes=notes or ["DART data loaded successfully."],
            ),
            metrics=metrics,
            valuation=valuation,
            scores=scores,
            risk_flags=risk_flags,
            hard_fail=hard_fail,
            final_label=final_label,
        )

    def screen(self, request: ScreenRequest) -> ScreenResponse:
        candidates = self._mock_candidates(request.market)
        filtered = [
            candidate
            for candidate in candidates
            if (candidate.market_cap or 0) >= request.min_market_cap
            and candidate.total_score >= request.min_total_score
        ]
        sorted_candidates = sorted(
            filtered, key=lambda candidate: candidate.total_score, reverse=True
        )
        limited = sorted_candidates[: request.limit]
        return ScreenResponse(market=request.market, candidates=limited, count=len(limited))

    def top_candidates(self, market: Market | None = None, limit: int = 10) -> list[Candidate]:
        markets = [market] if market else list(Market)
        candidates: list[Candidate] = []
        for candidate_market in markets:
            candidates.extend(self._mock_candidates(candidate_market))
        return sorted(candidates, key=lambda candidate: candidate.total_score, reverse=True)[:limit]

    def _data_reliability(
        self, results: list[FMPEndpointResult | DARTEndpointResult]
    ) -> float:
        if not results:
            return 0
        successful = sum(1 for result in results if result.ok and result.data not in (None, [], {}))
        return round(successful / len(results), 2)

    def _score_modules_from_fmp(
        self,
        metrics: FinancialMetrics,
        valuation: ValuationMetrics,
        reliability: float,
    ) -> ScoreModules:
        modules = self.scoring_engine.calculate_modules(metrics, valuation)
        reliability_floor = reliability * 100
        return ScoreModules(
            survival_risk_score=_blend_with_reliability(
                modules.survival_risk_score, reliability_floor
            ),
            moat_score=_blend_with_reliability(modules.moat_score, reliability_floor),
            pricing_power_score=_blend_with_reliability(
                modules.pricing_power_score, reliability_floor
            ),
            management_capital_allocation_score=_blend_with_reliability(
                modules.management_capital_allocation_score, reliability_floor
            ),
            buffett_fit_score=_blend_with_reliability(
                modules.buffett_fit_score, reliability_floor
            ),
            price_attractiveness_score=_blend_with_reliability(
                modules.price_attractiveness_score, reliability_floor
            ),
            future_vision_score=_blend_with_reliability(
                modules.future_vision_score, reliability_floor
            ),
            investment_efficiency_score=_blend_with_reliability(
                modules.investment_efficiency_score, reliability_floor
            ),
        )

    def _risk_flags(
        self,
        metrics: FinancialMetrics,
        valuation: ValuationMetrics,
        reliability: float,
        provider: str = "fmp",
    ) -> list[str]:
        flags: list[str] = []
        if reliability < 1:
            flags.append(f"partial_{provider}_data")
        if metrics.debt_to_equity is not None and metrics.debt_to_equity > 2:
            flags.append("high_debt_to_equity")
        if metrics.free_cash_flow_margin is not None and metrics.free_cash_flow_margin < 0:
            flags.append("negative_free_cash_flow_margin")
        if valuation.pe_ratio is not None and valuation.pe_ratio > 50:
            flags.append("high_pe_ratio")
        return flags


    def _dart_filing_risk_flags(self, filings: list[dict[str, Any]]) -> list[str]:
        patterns: dict[str, tuple[str, ...]] = {
            "paid_in_capital_increase": ("유상증자", "증자결정"),
            "convertible_bond": ("전환사채", "CB발행"),
            "bond_with_warrant": ("신주인수권부사채", "BW발행"),
            "audit_opinion_issue": ("감사의견", "의견거절", "한정의견", "부적정의견"),
            "trading_suspension_related": ("거래정지", "매매거래정지"),
            "major_shareholder_change": ("최대주주변경", "최대주주 변경"),
        }
        flags: list[str] = []
        for filing in filings:
            report_name = str(filing.get("report_nm") or "")
            for flag, keywords in patterns.items():
                if flag not in flags and any(keyword in report_name for keyword in keywords):
                    flags.append(flag)
        return flags

    def _mock_candidates(self, market: Market) -> list[Candidate]:
        tickers_by_market: dict[Market, list[tuple[str, str]]] = {
            Market.NASDAQ: [("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("ADBE", "Adobe")],
            Market.NYSE: [("BRK.B", "Berkshire Hathaway"), ("V", "Visa"), ("MA", "Mastercard")],
            Market.AMEX: [
                ("SPY", "SPDR S&P 500 ETF"),
                ("GLD", "SPDR Gold Shares"),
                ("IWM", "iShares Russell 2000 ETF"),
            ],
            Market.KOSPI: [
                ("005930", "Samsung Electronics"),
                ("000660", "SK hynix"),
                ("035420", "NAVER"),
            ],
            Market.KOSDAQ: [
                ("035900", "JYP Entertainment"),
                ("091990", "Celltrion Healthcare"),
                ("263750", "Pearl Abyss"),
            ],
        }
        base_scores = [88, 79, 64]
        candidates: list[Candidate] = []
        for index, (ticker, name) in enumerate(tickers_by_market[market]):
            modules = ScoreModules(
                survival_risk_score=86 - index * 5,
                moat_score=87 - index * 8,
                pricing_power_score=83 - index * 6,
                management_capital_allocation_score=82 - index * 7,
                buffett_fit_score=85 - index * 8,
                price_attractiveness_score=base_scores[index],
                future_vision_score=84 - index * 5,
                investment_efficiency_score=81 - index * 6,
            )
            scores = self.scoring_engine.calculate(modules)
            final_label = self.scoring_engine.final_label(
                scores.total_score,
                scores.BQS,
                scores.PAS,
                hard_fail=False,
            )
            company = CompanySummary(
                ticker=ticker,
                market=market,
                name=name,
                sector="Mock Sector",
                industry="Mock Industry",
                market_cap=100_000_000_000 / (index + 1),
            )
            candidates.append(
                Candidate(
                    ticker=company.ticker,
                    market=company.market,
                    company_name=company.name,
                    market_cap=company.market_cap,
                    total_score=scores.total_score,
                    BQS=scores.BQS,
                    PAS=scores.PAS,
                    VDS=scores.VDS,
                    EES=scores.EES,
                    data_reliability=0.5,
                    final_label=final_label,
                )
            )
        return candidates


def _dict_data(result: FMPEndpointResult | DARTEndpointResult) -> dict[str, Any]:
    return result.data if isinstance(result.data, dict) else {}


def _list_data(result: FMPEndpointResult | DARTEndpointResult) -> list[dict[str, Any]]:
    return result.data if isinstance(result.data, list) else []


def _score_positive(value: float | None, poor: float, excellent: float) -> float:
    if value is None:
        return 50
    if value <= poor:
        return 0
    if value >= excellent:
        return 100
    return round(((value - poor) / (excellent - poor)) * 100, 2)


def _score_inverse(value: float | None, excellent: float, poor: float) -> float:
    if value is None:
        return 50
    if value <= excellent:
        return 100
    if value >= poor:
        return 0
    return round(((poor - value) / (poor - excellent)) * 100, 2)


def _blend_with_reliability(score: float, reliability_floor: float) -> float:
    return round((score * 0.8) + (reliability_floor * 0.2), 2)
