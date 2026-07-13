from abc import ABC, abstractmethod

from app.domain.market.entities import AnalysisStatus, NewsItem, NewsSkipReason


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
    async def list_pending(self, limit: int) -> list[NewsItem]:
        """Return up to `limit` persisted items with `analysis_status = pending`,
        most-recent first."""
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
