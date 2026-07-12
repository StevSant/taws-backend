from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartPoint:
    """A single (x, y) point. `x` is an ISO-8601 timestamp string for time series, or a
    category label for distributions."""

    x: str
    y: float
