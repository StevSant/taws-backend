from dataclasses import replace

from app.domain.market.entities import AnalysisStatus, AssetClass, NewsItem
from app.domain.market.ports import NewsItemRepository, NewsProvider
from app.domain.signals.ports import SignalRepository


class IngestNews:
    """Persist-then-read pipeline backing `GET /api/v1/news` (issue #1).

    Fetches from the live/fixture `NewsProvider`, backfills `analysis_status` for
    brand-new items by checking whether a `Signal` already exists for any of their
    linked instruments (so an item about an already-classified instrument doesn't sit
    as a false "pending" forever), then persists via `NewsItemRepository.upsert_many` —
    which dedupes by URL and reads back the canonical, currently-persisted row for every
    item. That read-back is what makes `analysis_status` survive across requests: a
    later `AnalyzePendingNews` run's `analyzed`/`skipped` outcome is reflected the very
    next time this same article is fetched, instead of being recomputed from scratch.
    """

    def __init__(
        self,
        news_provider: NewsProvider,
        news_item_repository: NewsItemRepository,
        signal_repository: SignalRepository,
    ) -> None:
        self._news_provider = news_provider
        self._news_item_repository = news_item_repository
        self._signal_repository = signal_repository

    async def execute(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        fetched = await self._news_provider.fetch_news(
            symbols=symbols, asset_class=asset_class, since_hours=since_hours, limit=limit
        )
        prepared = await self._backfill_analysis_status(fetched)
        persisted = await self._news_item_repository.upsert_many(prepared)

        # `upsert_many` doesn't guarantee input order (it returns rows from a `SELECT ...
        # IN (urls)`); restore the provider's relevance/recency ordering before truncating
        # to `limit` again (a persisted item skipped by the read-back — e.g. a transient
        # write failure — would otherwise shift later items into its slot).
        order = {item.url: index for index, item in enumerate(fetched)}
        persisted.sort(key=lambda item: order.get(item.url, len(order)))
        return persisted[:limit]

    async def _backfill_analysis_status(self, items: list[NewsItem]) -> list[NewsItem]:
        """Best-effort default for items this pipeline hasn't seen before: if a `Signal`
        already exists for one of the item's linked instruments, seed it as `analyzed`
        (pointing at that signal) instead of `pending` — otherwise it would incorrectly
        read as "never analyzed" the first time it's persisted. Has no effect on items
        that already exist in the store (`upsert_many` never overwrites an existing row's
        `analysis_status`/`signal_id`).
        """
        symbols = {symbol for item in items for symbol in item.related_symbols}
        if not symbols:
            return items

        latest_signal_id_by_symbol: dict[str, str] = {}
        for symbol in symbols:
            existing = await self._signal_repository.list_for_instrument(symbol)
            if existing:
                latest_signal_id_by_symbol[symbol] = existing[0].id

        if not latest_signal_id_by_symbol:
            return items

        prepared = []
        for item in items:
            signal_id = next(
                (
                    latest_signal_id_by_symbol[symbol]
                    for symbol in item.related_symbols
                    if symbol in latest_signal_id_by_symbol
                ),
                None,
            )
            if signal_id is None:
                prepared.append(item)
            else:
                prepared.append(
                    replace(item, analysis_status=AnalysisStatus.ANALYZED, signal_id=signal_id)
                )
        return prepared
