from abc import ABC, abstractmethod
from datetime import date

from app.domain.market.entities import (
    AnalysisStatus,
    NewsBrowseQuery,
    NewsFacets,
    NewsItem,
    NewsSkipReason,
    PaginatedNewsItems,
)


class NewsItemRepository(ABC):
    """Port for persisting `NewsItem`s and their Analyst `analysis_status` (issue #1).

    Backs `GET /api/v1/news` (persist-then-read, so status survives across requests) and
    the batch analysis pipeline (`AnalyzePendingNews`, issue #2), which reads
    `list_pending` and writes back via `update_analysis_status`.
    """

    @abstractmethod
    async def upsert_many(self, items: list[NewsItem]) -> list[NewsItem]:
        """Persist every item not already known (deduped by `url`), then return the
        canonical, currently-persisted row for every `url` in `items` — whether just
        inserted or already existing. A pre-existing row's `analysis_status`/`signal_id`
        is never overwritten by this call; only brand-new rows take the values on `items`.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, news_id: str) -> NewsItem | None:
        """Return the persisted item with this id, or `None` if no such item exists.

        Backs `GET /api/v1/news/{id}` (issue #38) — single-item read by the persisted
        `news_items.id` (not the article `url`)."""
        raise NotImplementedError

    @abstractmethod
    async def browse(self, query: NewsBrowseQuery) -> PaginatedNewsItems:
        """Return one filtered/sorted page of persisted items plus the total count of the
        full filtered set (before pagination).

        Backs `GET /api/v1/news/browse` (issue #70) — a pure store read that never touches
        upstream providers, which is what lets it report an exact `total` and sort globally
        rather than within whatever slice a provider happened to return.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_facets(self) -> NewsFacets:
        """Return the distinct `source` and `provider` values present in the store, for the
        browse page's filter dropdowns."""
        raise NotImplementedError

    @abstractmethod
    async def list_recent(
        self, symbols: list[str] | None, since_hours: int, limit: int
    ) -> list[NewsItem]:
        """Return up to `limit` persisted items published within the last `since_hours`,
        newest first, optionally restricted to items linked to any of `symbols`.

        The DB-first read behind `GET /api/v1/news` (taws#71): serving the feed from what
        was already persisted keeps the endpoint off the synchronous upstream fan-out, so
        a cold provider cache can no longer blow past the client's request timeout. The
        upstream refresh that keeps this store warm runs out-of-band (`NewsFeedRefresher`).
        """
        raise NotImplementedError

    @abstractmethod
    async def list_pending(self, limit: int) -> list[NewsItem]:
        """Return up to `limit` persisted items with `analysis_status = pending`,
        most-recent first."""
        raise NotImplementedError

    @abstractmethod
    async def list_related(self, item: NewsItem, limit: int) -> list[NewsItem]:
        """Return up to `limit` other persisted items related to `item`, most-recent first.

        Backs the "related news" section of `GET /api/v1/news/{id}` (issue #57). Relatedness
        is a fallback chain, strongest signal first, because keying it purely off shared
        instruments left every article the linker couldn't map to a symbol — a large share of
        the RSS/Yahoo feed — with a permanently empty section:

        1. items sharing at least one `related_symbols` entry with `item`;
        2. items from the same `source`, when (1) returned fewer than `limit`;
        3. the most recent items overall, when (1) + (2) still returned fewer than `limit`.

        `item` itself is never included, and no item is returned twice.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_for_symbol_in_range(
        self, symbol: str, from_date: date, to_date: date, limit: int
    ) -> list[NewsItem]:
        """Return persisted items whose `related_symbols` include `symbol` and whose
        `published_at` falls within [from_date, to_date] (inclusive), most-recent first,
        up to `limit`. Backs date-windowed chat grounding — "why did this asset move in
        this period?" (issue #73 follow-up)."""
        raise NotImplementedError

    @abstractmethod
    async def update_analysis_status(
        self,
        news_item_id: str,
        status: AnalysisStatus,
        signal_id: str | None = None,
        skip_reason: NewsSkipReason | None = None,
    ) -> NewsItem:
        """Set `analysis_status` (and optionally `signal_id`/`skip_reason`) on one persisted item.

        Both optional arguments are written unconditionally, so omitting them clears whatever
        was there before — a freshly `analyzed` item must not keep the `skip_reason` from an
        earlier run that gated it (issue #26).
        """
        raise NotImplementedError
