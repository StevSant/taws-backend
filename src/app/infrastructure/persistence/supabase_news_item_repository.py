import asyncio
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from postgrest import AsyncSelectRequestBuilder, CountMethod
from supabase import AsyncClient

from app.domain.market.entities import (
    AnalysisStatus,
    NewsBrowseQuery,
    NewsFacets,
    NewsItem,
    NewsSkipReason,
    NewsSortField,
    PaginatedNewsItems,
    SentimentFilter,
    SortDirection,
)
from app.domain.market.ports import NewsItemRepository
from app.infrastructure.persistence.news_item_row_mapper import (
    news_item_from_row,
    news_item_to_insert_row,
)
from app.infrastructure.persistence.sentiment_filter_to_range import sentiment_filter_to_range
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache

_NEWS_ITEMS_TABLE = "news_items"
_DEFAULT_SENTIMENT_NEUTRAL_THRESHOLD = 0.15
# PostgREST's `or=(...)` grammar delimits filters with `,` and closes the group with `)`,
# and `%`/`*` are the `ilike` wildcards we supply ourselves — a search term carrying any of
# them would rewrite the filter rather than be matched by it. Dropped, not escaped: there is
# no useful headline search on those characters.
_SEARCH_RESERVED_CHARS = re.compile(r"[,()%*\"\\]")


class SupabaseNewsItemRepository(NewsItemRepository):
    """NewsItemRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `migrations/versions/0009_news_items.py` for the `news_items` schema. Not
    user-scoped — see that migration's RLS rationale (same "shared reference data,
    written via the service-role key" model as `signals`).
    """

    def __init__(
        self,
        supabase_url: str | None,
        supabase_key: str | None,
        sentiment_neutral_threshold: float = _DEFAULT_SENTIMENT_NEUTRAL_THRESHOLD,
    ) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)
        self._sentiment_neutral_threshold = sentiment_neutral_threshold

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

        # One backfill round-trip per item, fanned out concurrently: run sequentially this
        # was an N-round-trip await chain on the `GET /api/v1/news` request path, and with a
        # 50-item page it dominated the endpoint's latency (taws#71). Order between them is
        # irrelevant — each targets a distinct url.
        await asyncio.gather(
            *(self._backfill_image_url(client, item) for item in items if item.image_url),
            *(self._backfill_summary(client, item) for item in items if item.summary),
        )

        await self._backfill_categories(client, items)

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

    async def _backfill_summary(self, client: Any, item: NewsItem) -> None:
        """Same backfill-only shape as `_backfill_image_url`, for the same reason: rows
        ingested before `extract_rss_summary` landed were persisted with an empty summary
        (the feed's description was never read), and `ignore_duplicates` means a re-fetch
        would never repair them. Guarded on `summary = ''` so this can only ever fill a
        blank, never overwrite a real one."""
        await (
            client.table(_NEWS_ITEMS_TABLE)
            .update({"summary": item.summary})
            .eq("url", item.url)
            .eq("summary", "")
            .execute()
        )

    async def _backfill_categories(self, client: AsyncClient, items: list[NewsItem]) -> None:
        """Give a topical category (issue #69) to rows that don't have one yet.

        The insert above is `DO NOTHING` on conflict, so a row that predates migration 0018 —
        or that was persisted before this classifier existed — would keep `category = null`
        forever without this pass. `.is_("category", "null")` is what makes it a *backfill*
        rather than an overwrite: a row that already carries a category is never touched, so a
        human or a future smarter classifier can correct one without ingest stomping it back.

        Batched by category (one UPDATE per distinct category, at most `len(NewsCategory)`),
        rather than per item like the `image_url` loop above — that one needs a different value
        per row and has no choice; this one doesn't, and a per-item loop here would double the
        round trips `GET /api/v1/news` already makes.
        """
        urls_by_category: dict[str, list[str]] = defaultdict(list)
        for item in items:
            if item.category:
                urls_by_category[item.category.value].append(item.url)

        for category, urls in urls_by_category.items():
            await (
                client.table(_NEWS_ITEMS_TABLE)
                .update({"category": category})
                .in_("url", urls)
                .is_("category", "null")
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

    async def browse(self, query: NewsBrowseQuery) -> PaginatedNewsItems:
        """One filtered/sorted page plus an exact `total`, straight from the store.

        `count="exact"` makes PostgREST return the full filtered row count alongside the
        `.range()`d page — that's the number the numbered pager needs and the reason this
        endpoint reads the DB instead of the provider feed.
        """
        client = await self._clients.get()
        request = client.table(_NEWS_ITEMS_TABLE).select("*", count=CountMethod.exact)
        request = self._apply_filters(request, query)
        request = self._apply_order(request, query)

        start = query.offset
        response = await request.range(start, start + query.page_size - 1).execute()
        return PaginatedNewsItems(
            items=[news_item_from_row(row) for row in response.data],
            total=response.count or 0,
            page=query.page,
            page_size=query.page_size,
        )

    async def list_facets(self) -> NewsFacets:
        """Distinct `source`/`provider` values present in the store, for the browse dropdowns.

        PostgREST has no `select distinct`, so this reads both columns and dedupes here. At
        hackathon corpus size that's cheaper than adding an RPC, and it keeps the dropdowns
        honest: a value only appears if some row can actually be filtered down to it.
        """
        client = await self._clients.get()
        response = await client.table(_NEWS_ITEMS_TABLE).select("source, provider").execute()
        # `response.data` is typed as a JSON union, so indexing it by key doesn't type-check;
        # the row mappers in this package take the same escape hatch (`news_item_from_row`
        # accepts `Any`).
        rows = cast(list[dict[str, Any]], response.data)
        sources = sorted({row["source"] for row in rows if row.get("source")})
        providers = sorted({row["provider"] for row in rows if row.get("provider")})
        return NewsFacets(sources=sources, providers=providers)

    def _apply_filters(
        self, request: AsyncSelectRequestBuilder, query: NewsBrowseQuery
    ) -> AsyncSelectRequestBuilder:
        if query.symbols:
            # `overlaps` (PostgREST `ov`) — an item matches if ANY of its related symbols is
            # in the filter, which is what an asset-class filter (many symbols) means.
            request = request.overlaps("related_symbols", query.symbols)
        if query.source:
            request = request.eq("source", query.source)
        if query.provider:
            request = request.eq("provider", query.provider)
        if query.analysis_status is not None:
            request = request.eq("analysis_status", query.analysis_status.value)
        if query.category is not None:
            request = request.eq("category", query.category.value)
        if query.sentiment is not None:
            request = self._apply_sentiment(request, query.sentiment)

        term = _SEARCH_RESERVED_CHARS.sub(" ", query.search or "").strip()
        if term:
            request = request.or_(f"title.ilike.%{term}%,summary.ilike.%{term}%")

        cutoff = datetime.now(UTC) - timedelta(hours=query.since_hours)
        return request.gte("published_at", cutoff.isoformat())

    def _apply_sentiment(
        self, request: AsyncSelectRequestBuilder, sentiment: SentimentFilter
    ) -> AsyncSelectRequestBuilder:
        """`sentiment_score` is a numeric column, not a stored bucket — translate the bucket
        into the score range it stands for."""
        sentiment_range = sentiment_filter_to_range(sentiment, self._sentiment_neutral_threshold)
        if sentiment_range.is_null:
            return request.is_("sentiment_score", "null")
        if sentiment_range.gt is not None:
            return request.gt("sentiment_score", sentiment_range.gt)
        if sentiment_range.lt is not None:
            return request.lt("sentiment_score", sentiment_range.lt)
        return request.gte("sentiment_score", sentiment_range.gte).lte(
            "sentiment_score", sentiment_range.lte
        )

    def _apply_order(
        self, request: AsyncSelectRequestBuilder, query: NewsBrowseQuery
    ) -> AsyncSelectRequestBuilder:
        request = request.order(query.sort_by.value, desc=query.sort_dir is SortDirection.DESC)
        if query.sort_by is NewsSortField.PUBLISHED_AT:
            return request
        # Sorting by a low-cardinality column (source) leaves large ties, and PostgREST gives
        # no stable order within them — the same row could appear on two pages. Break the tie
        # on published_at so paging is deterministic.
        return request.order("published_at", desc=True)

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
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
        items = [news_item_from_row(row) for row in response.data]
        seen.update(news_item.id for news_item in items)
        return items

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
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [news_item_from_row(row) for row in response.data]

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
