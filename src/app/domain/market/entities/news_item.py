from dataclasses import dataclass, field
from datetime import datetime

from app.domain.market.entities.news_entity import NewsEntity


@dataclass(frozen=True, slots=True)
class NewsItem:
    """A single news article, optionally linked to one or more instruments.

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
    published_at: datetime
    related_symbols: list[str] = field(default_factory=list)
    entities: list[NewsEntity] = field(default_factory=list)
    sentiment_score: float | None = None
