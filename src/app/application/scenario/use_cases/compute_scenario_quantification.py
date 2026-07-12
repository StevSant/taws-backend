import asyncio
import logging
from typing import Literal

from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.use_cases.compute_event_study import ComputeEventStudy
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.domain.scenario.entities import ScenarioDirection, ScenarioSpec

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_PCT = 3.0
_MAX_COMPARABLE_SHOCK_PCT = 25.0


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
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._compute_event_study = ComputeEventStudy(market_data_provider, instrument_universe)

    async def execute(self, spec: ScenarioSpec) -> dict[str, EventStudyStats]:
        primary_symbol = spec.affected_symbols[0] if spec.affected_symbols else None
        results = await asyncio.gather(
            *(
                self._safe_event_study(
                    symbol,
                    spec if symbol == primary_symbol else None,
                )
                for symbol in spec.affected_symbols
            )
        )
        return {
            symbol: stats
            for symbol, stats in zip(spec.affected_symbols, results, strict=True)
            if stats is not None
        }

    async def _safe_event_study(
        self,
        symbol: str,
        spec: ScenarioSpec | None,
    ) -> EventStudyStats | None:
        try:
            threshold, implied_move = await self._scenario_threshold(symbol, spec)
            direction: Literal["up", "down"] | None = None
            if spec is not None and spec.direction == ScenarioDirection.UP:
                direction = "up"
            elif spec is not None and spec.direction == ScenarioDirection.DOWN:
                direction = "down"
            return await self._compute_event_study.execute(
                symbol,
                move_threshold_pct=threshold,
                move_direction=direction,
                probability_threshold_pct=implied_move,
                probability_horizon_days=(
                    spec.timeframe_days if spec is not None and spec.timeframe_days else 1
                ),
            )
        except Exception:
            logger.warning(
                "Scenario quantification: event study failed for %s.", symbol, exc_info=True
            )
            return None

    async def _scenario_threshold(
        self,
        symbol: str,
        spec: ScenarioSpec | None,
    ) -> tuple[float, float | None]:
        if spec is None or spec.target_price is None:
            return _DEFAULT_THRESHOLD_PCT, None
        instrument = self._instrument_universe.by_symbol(symbol)
        if instrument is None:
            return _DEFAULT_THRESHOLD_PCT, None
        current_price = await self._market_data_provider.get_last_price(instrument)
        if current_price is None or current_price <= 0:
            return _DEFAULT_THRESHOLD_PCT, None
        implied_move = abs((spec.target_price / current_price) - 1) * 100
        comparable_threshold = round(
            min(max(implied_move, _DEFAULT_THRESHOLD_PCT), _MAX_COMPARABLE_SHOCK_PCT), 2
        )
        return comparable_threshold, round(implied_move, 4)
