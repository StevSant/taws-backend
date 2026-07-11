from enum import StrEnum


class FearGreedClassification(StrEnum):
    """The alternative.me Crypto Fear & Greed Index's bucketed classification.

    Mirrors the exact five buckets alternative.me's API returns as `value_classification`
    (see `infrastructure/sentiment/parse_fear_greed_classification.py`), from most fearful
    to most greedy. Free-standing enum, own bounded context — not shared with
    `domain/market`'s `VolatilityLevel` or any other domain package's classification, same
    convention as `domain/scenario/entities/scenario_magnitude.py`.
    """

    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"
