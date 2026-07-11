import asyncio
import logging

from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.use_cases.compute_event_study import ComputeEventStudy
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.domain.scenario.entities import ScenarioSpec

logger = logging.getLogger(__name__)


class ComputeScenarioQuantification:
    """Scenario Lab Quantification step (issue #12): "last N similar events" statistics
    for every instrument a scenario affects.

    Reuses `ComputeEventStudy` (issue #7) directly — the same use case the `quant` chat
    specialist and `GET /api/v1/quant/event-study` call — rather than duplicating that
    math. Deliberately distinct from the Context gathering step (`GatherScenarioContext`,
    which covers current price/volatility via `ComputeMarketStats`): this step answers
    "how did similarly-sized past moves play out", not "what's happening right now".

    Fetches every affected instrument concurrently (`asyncio.gather`), degrading each
    individually to "no event-study data" on failure rather than failing the whole
    scenario run — same resilience shape as `GatherScenarioContext`.
    """

    def __init__(
        self, market_data_provider: MarketDataProvider, instrument_universe: InstrumentUniverse
    ) -> None:
        self._compute_event_study = ComputeEventStudy(market_data_provider, instrument_universe)

    async def execute(self, spec: ScenarioSpec) -> dict[str, EventStudyStats]:
        results = await asyncio.gather(
            *(self._safe_event_study(symbol) for symbol in spec.affected_symbols)
        )
        return {
            symbol: stats
            for symbol, stats in zip(spec.affected_symbols, results, strict=True)
            if stats is not None
        }

    async def _safe_event_study(self, symbol: str) -> EventStudyStats | None:
        try:
            return await self._compute_event_study.execute(symbol)
        except Exception:
            logger.warning(
                "Scenario quantification: event study failed for %s.", symbol, exc_info=True
            )
            return None
