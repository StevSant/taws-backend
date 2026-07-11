from dataclasses import dataclass
from datetime import datetime

from app.domain.market.entities.volatility_level import VolatilityLevel


@dataclass(frozen=True, slots=True)
class VolatilityRegime:
    """The current VIX level plus its derived `VolatilityLevel` bucket."""

    vix_level: float
    regime: VolatilityLevel
    as_of: datetime
