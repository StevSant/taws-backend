from dataclasses import dataclass

from app.application.quant.event_study_event import EventStudyEvent


@dataclass(frozen=True, slots=True)
class EventStudyStats:
    """Result of `ComputeEventStudy.execute(...)`: "last N similar events" statistics.

    `median_return_pct`/`min_return_pct`/`max_return_pct` are computed over ALL matched
    events (`sample_size`), even when `events` itself is truncated for display — see
    `ComputeEventStudy._MAX_EVENTS_RETURNED`. `None` for all three when `sample_size == 0`
    (no historical day in the lookback window moved by at least `move_threshold_pct`).
    """

    instrument_symbol: str
    lookback_days: int
    move_threshold_pct: float
    sample_size: int
    median_return_pct: float | None
    min_return_pct: float | None
    max_return_pct: float | None
    events: list[EventStudyEvent]
