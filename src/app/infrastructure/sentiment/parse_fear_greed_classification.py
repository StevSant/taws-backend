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

    Used by `AlternativeMeFearGreedProvider` to parse the API's exact wording.

    Raises `ValueError` on an unrecognized label rather than guessing — caught by
    `RoutingFearGreedProvider` like any other live-adapter failure, so a response we can't
    confidently interpret is reported as unavailable instead of being silently
    misclassified into a sentiment we never actually read.
    """
    key = raw_label.strip().lower()
    classification = _CLASSIFICATION_BY_LABEL.get(key)
    if classification is None:
        raise ValueError(f"[FearGreedProvider] Unknown Fear & Greed classification: {raw_label!r}")
    return classification
