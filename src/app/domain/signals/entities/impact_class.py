from enum import StrEnum


class ImpactClass(StrEnum):
    """The Analyst agent's classification of a news item's impact on an instrument."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"
