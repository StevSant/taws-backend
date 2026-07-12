from dataclasses import dataclass, field
from datetime import datetime

from app.domain.market.entities.news_entity import NewsEntity


@dataclass(frozen=True, slots=True)
class NewsItem:
    """A single news article, optionally linked to one or more instruments.

    `provider` is the fixed, stable identifier of the backend adapter that
    fetched this item (e.g. `"finnhub"`, `"marketaux"`), set unconditionally by
    every adapter. It is independent of `source`, which holds the article's
    own publisher/outlet name (e.g. "Economictimes.com") and can vary
    per-article even within the same provider.

    `entities` and `sentiment_score` are enrichment fields: providers that
    identify instruments in the text (e.g. Marketaux) populate them;
    `sentiment_score` is the average of the entity sentiments in [-1, +1].
    Plain sources leave them empty/None.
    """

    id: str
    title: str
    summary: str
    url: str
    source: str
    provider: str
    published_at: datetime
    related_symbols: list[str] = field(default_factory=list)
    entities: list[NewsEntity] = field(default_factory=list)
    sentiment_score: float | None = None
