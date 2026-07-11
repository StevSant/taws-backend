from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PriceCandle:
    """A single OHLC price bar. `volume` is optional — not every source has it."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
