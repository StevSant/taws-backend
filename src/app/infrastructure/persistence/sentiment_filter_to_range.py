from dataclasses import dataclass

from app.domain.market.entities import SentimentFilter


@dataclass(frozen=True, slots=True)
class SentimentRange:
    """The `sentiment_score` predicate one `SentimentFilter` bucket translates to.

    Exactly one shape is populated per bucket:
    - `is_null=True`      -> score IS NULL        (unclassified)
    - `gt` set            -> score > gt           (positive)
    - `lt` set            -> score < lt           (negative)
    - `gte` and `lte` set -> gte <= score <= lte  (neutral)
    """

    gt: float | None = None
    lt: float | None = None
    gte: float | None = None
    lte: float | None = None
    is_null: bool = False


def sentiment_filter_to_range(sentiment: SentimentFilter, threshold: float) -> SentimentRange:
    """Map a sentiment bucket to a `sentiment_score` predicate.

    `threshold` is the neutral band's half-width (`news_sentiment_neutral_threshold`),
    the same boundary the frontend's `classifyNewsSentiment` uses to badge a card — so
    the filter and the badge always agree on what "positive" means.
    """
    if sentiment is SentimentFilter.POSITIVE:
        return SentimentRange(gt=threshold)
    if sentiment is SentimentFilter.NEGATIVE:
        return SentimentRange(lt=-threshold)
    if sentiment is SentimentFilter.NEUTRAL:
        return SentimentRange(gte=-threshold, lte=threshold)
    return SentimentRange(is_null=True)
