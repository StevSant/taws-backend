from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MacroObservation:
    """A single macro-economic data point (e.g. one FRED series' latest reading)."""

    series_id: str
    value: float
    as_of: datetime
