from enum import StrEnum


class VolatilityLevel(StrEnum):
    """A bucketed VIX-derived volatility regime, from calmest to most stressed."""

    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
