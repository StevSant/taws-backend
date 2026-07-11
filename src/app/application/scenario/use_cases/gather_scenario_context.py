import asyncio
import logging

from app.application.analogs.use_cases import FindHistoricalAnalogs
from app.application.quant.market_stats import MarketStats
from app.application.quant.use_cases.compute_market_stats import ComputeMarketStats
from app.application.scenario.scenario_context import ScenarioContext
from app.domain.market.entities import MacroObservation, NewsItem, VolatilityRegime
from app.domain.market.ports import (
    InstrumentUniverse,
    MacroDataProvider,
    MarketDataProvider,
    NewsProvider,
)
from app.domain.scenario.entities import EvidenceType, ScenarioEvidence, ScenarioSpec
from app.domain.signals.entities import ImpactClass

logger = logging.getLogger(__name__)

# How far back to look for scenario-relevant news — wider than `GenerateSignal`'s default
# 48h, since a scenario's affected instruments may not have breaking news of their own
# right now; a scenario is hypothetical, not necessarily tied to a live headline.
_NEWS_SINCE_HOURS = 72
_NEWS_LIMIT = 10


class GatherScenarioContext:
    """Scenario Lab Context gathering step (issue #12): fetches current prices/
    volatility, related news, macro state, and historical analogs, all in parallel.

    Fans out to every source concurrently via `asyncio.gather` (per the issue's explicit
    guidance) and degrades each source independently: a failed fetch never crashes the
    whole step, it just leaves that field `None`/empty in the returned `ScenarioContext`
    — same resilience pattern as `GenerateSignal._compute_price_delta`'s
    try/except-degrade-to-None. In practice most of these ports already self-heal at the
    infrastructure layer (`RoutingMarketDataProvider`/`RoutingMacroDataProvider`/
    `AggregatingNewsProvider` all fall back to a fixture on failure), but this step adds
    its own guard anyway per the issue's explicit resilience requirement.

    Reuses `ComputeMarketStats` (issue #7) for prices/volatility rather than duplicating
    that math — the same use case the `quant` chat specialist and
    `GET /api/v1/quant/stats` call. `ComputeEventStudy` (the "last N similar events"
    statistic) is deliberately NOT called here — that's the separate Quantification step
    (`ComputeScenarioQuantification`), so the two steps don't duplicate the same
    computation.
    """

    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        news_provider: NewsProvider,
        macro_data_provider: MacroDataProvider,
        find_historical_analogs: FindHistoricalAnalogs,
    ) -> None:
        self._compute_market_stats = ComputeMarketStats(market_data_provider, instrument_universe)
        self._news_provider = news_provider
        self._macro_data_provider = macro_data_provider
        self._find_historical_analogs = find_historical_analogs

    async def execute(self, spec: ScenarioSpec) -> ScenarioContext:
        market_stats_task = asyncio.gather(
            *(self._safe_market_stats(symbol) for symbol in spec.affected_symbols)
        )
        analogs_task = asyncio.gather(
            *(self._safe_analogs(symbol, spec) for symbol in spec.affected_symbols)
        )

        (
            market_stats_results,
            analog_results,
            news_items,
            macro_rates,
            macro_cpi,
            volatility_regime,
        ) = await asyncio.gather(
            market_stats_task,
            analogs_task,
            self._safe_news(spec),
            self._safe_rates(),
            self._safe_cpi(),
            self._safe_volatility_regime(),
        )

        market_stats = {
            symbol: stats
            for symbol, stats in zip(spec.affected_symbols, market_stats_results, strict=True)
            if stats is not None
        }
        historical_analogs = {
            symbol: evidence
            for symbol, evidence in zip(spec.affected_symbols, analog_results, strict=True)
            if evidence
        }

        return ScenarioContext(
            market_stats=market_stats,
            news_items=news_items,
            macro_rates=macro_rates,
            macro_cpi=macro_cpi,
            volatility_regime=volatility_regime,
            historical_analogs=historical_analogs,
        )

    async def _safe_market_stats(self, symbol: str) -> MarketStats | None:
        try:
            return await self._compute_market_stats.execute(symbol)
        except Exception:
            logger.warning(
                "Scenario context: market stats fetch failed for %s.", symbol, exc_info=True
            )
            return None

    async def _safe_analogs(self, symbol: str, spec: ScenarioSpec) -> list[ScenarioEvidence]:
        # `FindHistoricalAnalogs.execute` never raises (see its own docstring), but this
        # runs before the Synthesis step has classified any impact direction yet, so
        # `ImpactClass.UNCERTAIN` is used as a neutral query token — `VectorStore.search`
        # has no filter parameter anyway (a pure top-k-nearest lookup), so this only
        # affects the embedded query text, not result filtering.
        analogs = await self._find_historical_analogs.execute(
            symbol, ImpactClass.UNCERTAIN, spec.description
        )
        # `SignalEvidence.detail` is typed `str | None` in general, but
        # `find_historical_analogs.py`'s `_to_evidence` always sets it for a real match —
        # the `or ""` is a type-level safety net, not an expected runtime path.
        return [
            ScenarioEvidence(evidence_type=EvidenceType.HISTORICAL_ANALOG, detail=item.detail or "")
            for item in analogs
        ]

    async def _safe_news(self, spec: ScenarioSpec) -> list[NewsItem]:
        if not spec.affected_symbols:
            return []
        try:
            return await self._news_provider.fetch_news(
                symbols=spec.affected_symbols, since_hours=_NEWS_SINCE_HOURS, limit=_NEWS_LIMIT
            )
        except Exception:
            logger.warning("Scenario context: news fetch failed.", exc_info=True)
            return []

    async def _safe_rates(self) -> MacroObservation | None:
        try:
            return await self._macro_data_provider.get_rates()
        except Exception:
            logger.warning("Scenario context: macro rates fetch failed.", exc_info=True)
            return None

    async def _safe_cpi(self) -> MacroObservation | None:
        try:
            return await self._macro_data_provider.get_cpi()
        except Exception:
            logger.warning("Scenario context: macro CPI fetch failed.", exc_info=True)
            return None

    async def _safe_volatility_regime(self) -> VolatilityRegime | None:
        try:
            return await self._macro_data_provider.get_volatility_regime()
        except Exception:
            logger.warning("Scenario context: volatility regime fetch failed.", exc_info=True)
            return None
