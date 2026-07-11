from datetime import UTC, datetime

from app.domain.market.entities import NewsEntity, NewsItem


def map_marketaux_article(article: dict) -> NewsItem:
    """Map one Marketaux `/news/all` article payload onto the domain `NewsItem`.

    Entity linkage and per-entity sentiment come straight from Marketaux; the
    article-level `sentiment_score` is the average of the entity sentiments.
    """
    entities = [
        NewsEntity(
            symbol=raw["symbol"],
            name=raw.get("name") or "",
            entity_type=raw.get("type") or "",
            industry=raw.get("industry"),
            match_score=raw.get("match_score"),
            sentiment_score=raw.get("sentiment_score"),
        )
        for raw in article.get("entities") or []
        if raw.get("symbol")
    ]
    return NewsItem(
        id=article.get("uuid") or article.get("url") or "",
        title=article.get("title") or "",
        summary=article.get("description") or article.get("snippet") or "",
        url=article.get("url") or "",
        source=article.get("source") or "",
        published_at=_parse_published_at(article.get("published_at")),
        related_symbols=[entity.symbol for entity in entities],
        entities=entities,
        sentiment_score=_average_sentiment(entities),
    )


def _parse_published_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _average_sentiment(entities: list[NewsEntity]) -> float | None:
    scores = [e.sentiment_score for e in entities if e.sentiment_score is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)
