from enum import StrEnum


class SentimentFilter(StrEnum):
    """Sentiment buckets for the news browse filter.

    Derived from `news_items.sentiment_score` ranges rather than a stored column —
    see `sentiment_filter_to_range`. `UNCLASSIFIED` matches rows with no score at
    all (sources that don't enrich), which is an honest "we don't know" rather
    than a defaulted neutral.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCLASSIFIED = "unclassified"
