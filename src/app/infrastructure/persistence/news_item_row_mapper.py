from typing import Any

from app.domain.market.entities import AnalysisStatus, NewsEntity, NewsItem
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def news_item_from_row(row: Any) -> NewsItem:
    """Map one `news_items` table row (as returned by `supabase-py`) onto `NewsItem`.

    `entities` is stored as a JSONB array; PostgREST already decodes it into a
    `list[dict]`, so no extra JSON parsing is needed here — same shape as
    `signal_row_mapper.signal_from_row`'s `evidence` handling.
    """
    return NewsItem(
        id=row["id"],
        title=row["title"],
        summary=row["summary"],
        url=row["url"],
        source=row["source"],
        provider=row["provider"],
        published_at=parse_supabase_timestamp(row["published_at"]),
        related_symbols=list(row.get("related_symbols") or []),
        entities=[_entity_from_row(item) for item in row.get("entities") or []],
        sentiment_score=row.get("sentiment_score"),
        analysis_status=AnalysisStatus(row["analysis_status"]),
        signal_id=row.get("signal_id"),
    )


def news_item_to_insert_row(item: NewsItem) -> dict[str, Any]:
    """Map a `NewsItem` onto an insert row for `news_items`.

    Deliberately omits `id`: provider-supplied `NewsItem.id` values aren't guaranteed to
    be valid UUIDs (e.g. `NewsApiNewsProvider`/`RssNewsProvider` set `id` to the article
    URL) — the `news_items.id` column's `gen_random_uuid()` default generates the real,
    stable persisted id instead.
    """
    return {
        "title": item.title,
        "summary": item.summary,
        "url": item.url,
        "source": item.source,
        "provider": item.provider,
        "published_at": item.published_at.isoformat(),
        "related_symbols": item.related_symbols,
        "entities": [_entity_to_row(entity) for entity in item.entities],
        "sentiment_score": item.sentiment_score,
        "analysis_status": item.analysis_status.value,
        "signal_id": item.signal_id,
    }


def _entity_from_row(row: dict[str, Any]) -> NewsEntity:
    return NewsEntity(
        symbol=row["symbol"],
        name=row["name"],
        entity_type=row["entity_type"],
        industry=row.get("industry"),
        match_score=row.get("match_score"),
        sentiment_score=row.get("sentiment_score"),
    )


def _entity_to_row(entity: NewsEntity) -> dict[str, Any]:
    return {
        "symbol": entity.symbol,
        "name": entity.name,
        "entity_type": entity.entity_type,
        "industry": entity.industry,
        "match_score": entity.match_score,
        "sentiment_score": entity.sentiment_score,
    }
