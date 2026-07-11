from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewsEntity:
    """An instrument identified within a news article, with enrichment scores.

    `sentiment_score` is in [-1, +1] (negative → negative tone); `match_score`
    is the provider's confidence that the article is actually about this
    entity. Both are optional — plain sources (e.g. RSS) can't provide them.
    """

    symbol: str
    name: str
    entity_type: str
    industry: str | None = None
    match_score: float | None = None
    sentiment_score: float | None = None
