import statistics

from app.application.quant.compute_daily_returns import compute_daily_returns
from app.application.quant.event_study_event import EventStudyEvent
from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
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
    ) -> EventStudyStats:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        series = await self._market_data_provider.get_price_series(instrument, lookback_days)
        return_pairs = compute_daily_returns(series.candles)

        matched = [
            EventStudyEvent(date=candle.timestamp, return_pct=round(daily_return, 4))
            for candle, daily_return in return_pairs
            if abs(daily_return) >= move_threshold_pct
        ]
        magnitudes = [event.return_pct for event in matched]

        return EventStudyStats(
            instrument_symbol=instrument.symbol,
            lookback_days=lookback_days,
            move_threshold_pct=move_threshold_pct,
            sample_size=len(matched),
            median_return_pct=statistics.median(magnitudes) if magnitudes else None,
            min_return_pct=min(magnitudes) if magnitudes else None,
            max_return_pct=max(magnitudes) if magnitudes else None,
            events=matched[-_MAX_EVENTS_RETURNED:],
        )
