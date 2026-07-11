from app.domain.sentiment.entities import FearGreedClassification

_CLASSIFICATION_BY_LABEL = {
    "extreme fear": FearGreedClassification.EXTREME_FEAR,
    "fear": FearGreedClassification.FEAR,
    "neutral": FearGreedClassification.NEUTRAL,
    "greed": FearGreedClassification.GREED,
    "extreme greed": FearGreedClassification.EXTREME_GREED,
}


def parse_fear_greed_classification(raw_label: str) -> FearGreedClassification:
    """Map alternative.me's `value_classification` string (e.g. `"Extreme Fear"`) to
    `FearGreedClassification`.

    Shared by `AlternativeMeFearGreedProvider` (live, parses the API's exact wording)
    and `FixtureFearGreedProvider` (parses `Settings.fixture_fear_greed_classification`)
    so the mapping never drifts between the two — same "shared bucketing/parsing helper
    reused by live + fixture adapter" pattern as
    `infrastructure/macro/bucket_volatility_regime.py`.

    Raises `ValueError` on an unrecognized label rather than guessing — caught by
    `RoutingFearGreedProvider` like any other live-adapter failure, so a live API
    response we can't confidently interpret degrades to the fixture instead of being
    silently misclassified.
    """
    key = raw_label.strip().lower()
    classification = _CLASSIFICATION_BY_LABEL.get(key)
    if classification is None:
        raise ValueError(f"[FearGreedProvider] Unknown Fear & Greed classification: {raw_label!r}")
    return classification
