from dataclasses import dataclass, field
from datetime import date

_FALLBACK_DAYS = 365


@dataclass(frozen=True, slots=True)
class ChartConfig:
    """Config-derived chart limits/options, built once in the DI container from Settings
    and injected into every chart use case — so no timeframe/threshold is hardcoded in
    use-case code."""

    default_timeframe: str
    max_points: int
    available_timeframes: list[str] = field(default_factory=list)
    timeframe_days: dict[str, int] = field(default_factory=dict)

    def days_for(self, timeframe: str) -> int:
        """Resolve a timeframe label to a day count, falling back to the default."""
        return self.timeframe_days.get(
            timeframe, self.timeframe_days.get(self.default_timeframe, _FALLBACK_DAYS)
        )

    @property
    def max_days(self) -> int:
        """The widest configured fetch window, in days (e.g. the `max` timeframe)."""
        return max(self.timeframe_days.values(), default=_FALLBACK_DAYS)

    def fetch_days_for_range(self, from_date: date, today: date) -> int:
        """Days of history to fetch so a custom range reaching back to `from_date` is covered.

        The market-data port fetches by a trailing day count only, so a custom range is
        served by fetching wide (from today back past `from_date`) then slicing. The window
        is capped at `max_days` — a range older than the widest configured window returns
        only the portion that fetch covers, never an unbounded request."""
        span = (today - from_date).days + 1
        return max(1, min(span, self.max_days))
