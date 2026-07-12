import statistics
from typing import Literal

from app.application.quant.compute_daily_returns import compute_daily_returns
from app.application.quant.event_study_event import EventStudyEvent
from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.domain.market.entities import PriceCandle
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider

_DEFAULT_LOOKBACK_DAYS = 365

# A day counts as a "similar event" when the magnitude of its close-over-close return
# is at least this many percentage points. Fixed rather than volatility-relative (unlike
# `compute_market_stats.py`'s z-score threshold): an event study answers "how did big
# moves like *this one* play out", so the bar is an absolute move size, not relative to
# the instrument's own recent calm/turbulence.
_DEFAULT_MOVE_THRESHOLD_PCT = 3.0

# Caps how many matched event days are returned in `EventStudyStats.events`, so a long
# lookback on a volatile instrument doesn't blow up the tool/response payload. Does NOT
# affect `sample_size`/`median_return_pct`/`min_return_pct`/`max_return_pct`, which are
# always computed over every matched event.
_MAX_EVENTS_RETURNED = 20


class ComputeEventStudy:
    """Quant pipeline: historical price history -> "last N similar events" statistics.

    Reusable core logic for issue #7 (Quant Analyst, T1) — answers the acceptance
    criterion's "last N similar events: median X%, range Y...Z%" shape. Same reuse
    rationale as `ComputeMarketStats`: called directly by the `quant` chat specialist's
    grounding tool (`infrastructure/agents/tools/get_event_study_stats_tool.py`), by
    `GET /api/v1/quant/event-study`, and available for the future Scenario Simulation
    graph (issue #12) to call without duplicating this math.

    "Similar events" (T1 simplification — see issue #7's design guidance): same
    -instrument trading days from the last `lookback_days` whose close-over-close return
    magnitude is >= `move_threshold_pct`. Each matched day's own return is the event's
    reported outcome — this is deliberately NOT a forward-N-day return study, and NOT a
    cross-instrument or cross-event-type historical-analogs match (that's issue #15's
    pgvector/embeddings scope, out of bounds here). A future forward-return event study
    can extend this use case without changing what today's `EventStudyEvent.return_pct`
    means.

    Constructor-injected with `MarketDataProvider` + `InstrumentUniverse` — no new port
    method needed, same as `ComputeMarketStats`. Never raises on live-data trouble for
    the same reason (`RoutingMarketDataProvider`'s fixture fallback); only an unknown
    instrument symbol raises (`UnknownInstrumentError`). A `sample_size` of `0` (no
    matching event in the window) is a valid, non-error result.
    """

    def __init__(
        self, market_data_provider: MarketDataProvider, instrument_universe: InstrumentUniverse
    ) -> None:
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe

    async def execute(
        self,
        instrument_symbol: str,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        move_threshold_pct: float = _DEFAULT_MOVE_THRESHOLD_PCT,
        move_direction: Literal["up", "down"] | None = None,
        probability_threshold_pct: float | None = None,
        probability_horizon_days: int = 1,
    ) -> EventStudyStats:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        series = await self._market_data_provider.get_price_series(instrument, lookback_days)
        return_pairs = compute_daily_returns(series.candles)

        matched_with_indices = [
            (
                candle_index,
                EventStudyEvent(date=candle.timestamp, return_pct=round(daily_return, 4)),
            )
            for candle_index, (candle, daily_return) in enumerate(return_pairs, start=1)
            if _matches_move(daily_return, move_threshold_pct, move_direction)
        ]
        matched = [event for _, event in matched_with_indices]
        matched_indices = [index for index, _ in matched_with_indices]
        magnitudes = [event.return_pct for event in matched]
        probability, probability_sample_size, probability_occurrences = (
            _estimate_scenario_probability(
                series.candles,
                probability_threshold_pct,
                probability_horizon_days,
                move_direction,
            )
        )

        return EventStudyStats(
            instrument_symbol=instrument.symbol,
            lookback_days=lookback_days,
            move_threshold_pct=move_threshold_pct,
            sample_size=len(matched),
            median_return_pct=statistics.median(magnitudes) if magnitudes else None,
            min_return_pct=min(magnitudes) if magnitudes else None,
            max_return_pct=max(magnitudes) if magnitudes else None,
            forward_1d_median_pct=_median_forward_return(
                series.candles, matched_indices, horizon_days=1
            ),
            forward_7d_median_pct=_median_forward_return(
                series.candles, matched_indices, horizon_days=7
            ),
            forward_30d_median_pct=_median_forward_return(
                series.candles, matched_indices, horizon_days=30
            ),
            scenario_probability_pct=probability,
            scenario_probability_sample_size=probability_sample_size,
            scenario_probability_occurrences=probability_occurrences,
            scenario_probability_horizon_days=(
                probability_horizon_days if probability_threshold_pct is not None else None
            ),
            scenario_probability_threshold_pct=probability_threshold_pct,
            events=matched[-_MAX_EVENTS_RETURNED:],
        )


def _matches_move(
    daily_return: float,
    threshold_pct: float,
    direction: Literal["up", "down"] | None,
) -> bool:
    if direction == "up":
        return daily_return >= threshold_pct
    if direction == "down":
        return daily_return <= -threshold_pct
    return abs(daily_return) >= threshold_pct


def _median_forward_return(
    candles: list[PriceCandle],
    event_indices: list[int],
    horizon_days: int,
) -> float | None:
    outcomes = []
    for event_index in event_indices:
        future_index = event_index + horizon_days
        if future_index >= len(candles):
            continue
        event_close = candles[event_index].close
        if event_close == 0:
            continue
        future_close = candles[future_index].close
        outcomes.append(((future_close / event_close) - 1) * 100)
    return round(statistics.median(outcomes), 4) if outcomes else None


def _estimate_scenario_probability(
    candles: list[PriceCandle],
    threshold_pct: float | None,
    horizon_days: int,
    direction: Literal["up", "down"] | None,
) -> tuple[float | None, int, int]:
    if threshold_pct is None or threshold_pct <= 0 or horizon_days < 1:
        return None, 0, 0
    sample_size = max(len(candles) - horizon_days, 0)
    if sample_size == 0:
        return None, 0, 0
    occurrences = 0
    for start_index in range(sample_size):
        start_close = candles[start_index].close
        if start_close == 0:
            continue
        end_close = candles[start_index + horizon_days].close
        move_pct = ((end_close / start_close) - 1) * 100
        if _matches_move(move_pct, threshold_pct, direction):
            occurrences += 1
    return round((occurrences / sample_size) * 100, 4), sample_size, occurrences
