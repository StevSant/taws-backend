from dataclasses import dataclass, field


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
            timeframe, self.timeframe_days.get(self.default_timeframe, 365)
        )
