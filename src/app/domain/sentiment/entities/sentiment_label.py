from enum import StrEnum


class SentimentLabel(StrEnum):
    """A categorical readout of a `SentimentReading.tone_score`.

    Deterministically bucketed from `tone_score` by `AnalyzeSentiment` (via
    `Settings.sentiment_bullish_threshold` / `sentiment_bearish_threshold`), never
    chosen by the model directly — same "deterministic bucketing next to a raw model/
    vendor number" discipline as `infrastructure/macro/bucket_volatility_regime.py`
    bucketing VIX into `VolatilityLevel`. Free-standing enum: market "tone" (bearish/
    bullish) is a distinct vocabulary from `domain/signals`' `ImpactClass` (an
    instrument-impact call), same "own bounded context" convention as
    `domain/scenario/entities/scenario_magnitude.py`.
    """

    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
