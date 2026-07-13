<<<<<<< HEAD
from collections.abc import Callable
from typing import Any
=======
from datetime import date, timedelta
>>>>>>> d9c5b05 (feat(chat): ground the answer on the asset's news in a selected date window (#73))

from app.domain.market.entities import AnalysisStatus, NewsItem, NewsSkipReason
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

        for item in items:
            if item.image_url:
                await (
                    client.table(_NEWS_ITEMS_TABLE)
                    .update({"image_url": item.image_url})
                    .eq("url", item.url)
                    .is_("image_url", "null")
                    .execute()
                )
            # Same backfill-only shape as `image_url` above, for the same reason: rows
            # ingested before `extract_rss_summary` landed were persisted with an empty
            # summary (the feed's description was never read), and `ignore_duplicates`
            # means a re-fetch would never repair them. Guarded on `summary = ''` so this
            # can only ever fill a blank, never overwrite a real one.
            if item.summary:
                await (
                    client.table(_NEWS_ITEMS_TABLE)
                    .update({"summary": item.summary})
                    .eq("url", item.url)
                    .eq("summary", "")
                    .execute()
                )

        urls = [item.url for item in items]
        response = await client.table(_NEWS_ITEMS_TABLE).select("*").in_("url", urls).execute()
        persisted = [news_item_from_row(row) for row in response.data]
        by_url = {news_item.url: news_item for news_item in persisted}
        return [by_url[item.url] for item in items if item.url in by_url]

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

<<<<<<< HEAD
    async def list_related(self, item: NewsItem, limit: int) -> list[NewsItem]:
        """Shared-symbol matches first, then same-source, then plain recency — see the port
        for why the fallback chain exists. Each tier is a separate query rather than one
        `or(...)` filter so the tiers stay *ordered by strength*: PostgREST would sort a
        combined result by `published_at` alone, letting an unrelated-but-newer article
        outrank a genuine shared-symbol match.
        """
        related: list[NewsItem] = []
        seen = {item.id}

        if item.related_symbols:
            related += await self._select_related(
                seen,
                limit - len(related),
                lambda query: query.overlaps("related_symbols", item.related_symbols),
            )
        if len(related) < limit:
            related += await self._select_related(
                seen, limit - len(related), lambda query: query.eq("source", item.source)
            )
        if len(related) < limit:
            related += await self._select_related(seen, limit - len(related), lambda query: query)
        return related

    async def _select_related(
        self,
        seen: set[str],
        limit: int,
        narrow: Callable[[Any], Any],
    ) -> list[NewsItem]:
        """Run one tier of `list_related`: the newest `limit` items matching `narrow`, minus
        everything already collected. Mutates `seen` so the next tier can't re-serve them.
        """
        if limit <= 0:
            return []
        client = await self._clients.get()
        query = narrow(client.table(_NEWS_ITEMS_TABLE).select("*"))
        response = (
            await query.not_.in_("id", list(seen))
=======
    async def list_for_symbol_in_range(
        self, symbol: str, from_date: date, to_date: date, limit: int
    ) -> list[NewsItem]:
        client = await self._clients.get()
        response = (
            await client.table(_NEWS_ITEMS_TABLE)
            .select("*")
            .contains("related_symbols", [symbol])
            .gte("published_at", from_date.isoformat())
            .lt("published_at", (to_date + timedelta(days=1)).isoformat())
>>>>>>> d9c5b05 (feat(chat): ground the answer on the asset's news in a selected date window (#73))
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
<<<<<<< HEAD
        items = [news_item_from_row(row) for row in response.data]
        seen.update(news_item.id for news_item in items)
        return items
=======
        return [news_item_from_row(row) for row in response.data]
>>>>>>> d9c5b05 (feat(chat): ground the answer on the asset's news in a selected date window (#73))

    async def update_analysis_status(
        self,
        news_item_id: str,
        status: AnalysisStatus,
        signal_id: str | None = None,
        skip_reason: NewsSkipReason | None = None,
    ) -> NewsItem:
        """Both `signal_id` and `skip_reason` are written unconditionally, so an item that
        was previously gated and is now `analyzed` doesn't keep a stale `skip_reason` (and
        vice-versa) — see the port's contract."""
        client = await self._clients.get()
        response = (
            await client.table(_NEWS_ITEMS_TABLE)
            .update(
                {
                    "analysis_status": status.value,
                    "signal_id": signal_id,
                    "skip_reason": skip_reason.value if skip_reason else None,
                }
            )
            .eq("id", news_item_id)
            .execute()
        )
        return news_item_from_row(response.data[0])
