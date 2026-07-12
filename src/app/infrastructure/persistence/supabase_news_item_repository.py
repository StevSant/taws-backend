import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.market.entities import AnalysisStatus, NewsItem
from app.domain.market.ports import NewsItemRepository
from app.infrastructure.persistence.news_item_row_mapper import (
    news_item_from_row,
    news_item_to_insert_row,
)
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache

_NEWS_ITEMS_TABLE = "news_items"


class SupabaseNewsItemRepository(NewsItemRepository):
    """NewsItemRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `migrations/versions/0009_news_items.py` for the `news_items` schema. Not
    user-scoped — see that migration's RLS rationale (same "shared reference data,
    written via the service-role key" model as `signals`).
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def upsert_many(self, items: list[NewsItem]) -> list[NewsItem]:
        """Insert every item not already known by `url` (`ON CONFLICT (url) DO NOTHING`,
        via `ignore_duplicates=True`), then read back the canonical, currently-persisted
        row for every url in `items`. The follow-up SELECT is what guarantees a caller
        always sees the real, current `analysis_status` — including for urls that
        already existed and were therefore left untouched by the insert — rather than
        whatever backfilled guess `items` happened to carry in for them.
        """
        if not items:
            return []

        client = await self._clients.get()
        rows = [news_item_to_insert_row(item) for item in items]
        await (
            client.table(_NEWS_ITEMS_TABLE)
            .upsert(rows, on_conflict="url", ignore_duplicates=True)
            .execute()
        )

        # One backfill round-trip per image-bearing item, fanned out concurrently: run
        # sequentially this was an N-round-trip await chain on the `GET /api/v1/news`
        # request path, and with a 50-item page it dominated the endpoint's latency
        # (taws#71). Order between them is irrelevant — each targets a distinct url.
        await asyncio.gather(
            *(self._backfill_image_url(client, item) for item in items if item.image_url)
        )

        urls = [item.url for item in items]
        response = await client.table(_NEWS_ITEMS_TABLE).select("*").in_("url", urls).execute()
        persisted = [news_item_from_row(row) for row in response.data]
        by_url = {news_item.url: news_item for news_item in persisted}
        return [by_url[item.url] for item in items if item.url in by_url]

    async def _backfill_image_url(self, client: Any, item: NewsItem) -> None:
        """Fill in `image_url` on an already-persisted row that has none — a later fetch of
        the same article (via a provider that does carry images) enriches the stored row,
        while never overwriting an image already on it (`.is_("image_url", "null")`)."""
        await (
            client.table(_NEWS_ITEMS_TABLE)
            .update({"image_url": item.image_url})
            .eq("url", item.url)
            .is_("image_url", "null")
            .execute()
        )

    async def list_recent(
        self, symbols: list[str] | None, since_hours: int, limit: int
    ) -> list[NewsItem]:
        client = await self._clients.get()
        cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
        query = client.table(_NEWS_ITEMS_TABLE).select("*").gte("published_at", cutoff.isoformat())
        if symbols:
            # `related_symbols` is a `text[]` (migration 0009) — `overlaps` is the array
            # `&&` operator, i.e. "linked to at least one of these instruments".
            query = query.overlaps("related_symbols", symbols)
        response = await query.order("published_at", desc=True).limit(limit).execute()
        return [news_item_from_row(row) for row in response.data]

    async def get_by_id(self, news_id: str) -> NewsItem | None:
        client = await self._clients.get()
        response = await client.table(_NEWS_ITEMS_TABLE).select("*").eq("id", news_id).execute()
        return news_item_from_row(response.data[0]) if response.data else None

    async def list_pending(self, limit: int) -> list[NewsItem]:
        client = await self._clients.get()
        response = (
            await client.table(_NEWS_ITEMS_TABLE)
            .select("*")
            .eq("analysis_status", AnalysisStatus.PENDING.value)
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [news_item_from_row(row) for row in response.data]

    async def update_analysis_status(
        self, news_item_id: str, status: AnalysisStatus, signal_id: str | None = None
    ) -> NewsItem:
        client = await self._clients.get()
        response = (
            await client.table(_NEWS_ITEMS_TABLE)
            .update({"analysis_status": status.value, "signal_id": signal_id})
            .eq("id", news_item_id)
            .execute()
        )
        return news_item_from_row(response.data[0])
