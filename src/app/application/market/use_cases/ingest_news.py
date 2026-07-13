import logging
from dataclasses import replace

from app.application.market.use_cases.classify_news_category import classify_news_category
from app.domain.market.entities import AnalysisStatus, AssetClass, NewsItem
from app.domain.market.ports import NewsItemRepository, NewsProvider
from app.domain.signals.ports import SignalRepository

logger = logging.getLogger(__name__)


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
        categorized = self._classify_categories(fetched)
        prepared = await self._backfill_analysis_status(categorized)
        persisted = await self._persist(prepared)

        # `upsert_many` doesn't guarantee input order (it returns rows from a `SELECT ...
        # IN (urls)`); restore the provider's relevance/recency ordering before truncating
        # to `limit` again (a persisted item skipped by the read-back — e.g. a transient
        # write failure — would otherwise shift later items into its slot).
        order = {item.url: index for index, item in enumerate(fetched)}
        persisted.sort(key=lambda item: order.get(item.url, len(order)))
        return persisted[:limit]

    def _classify_categories(self, items: list[NewsItem]) -> list[NewsItem]:
        """Assign each item its topical category (issue #69).

        Runs on the ingest path, *not* the analysis path, which is the whole point: the
        classifier is a pure keyword scorer with no LLM call, so every item gets a category
        even when it is later gated out of signal generation and no `Signal` is ever produced
        for it. Being synchronous and offline, it costs nothing and adds no latency here.

        Providers never populate `category`, so this always computes it; `upsert_many` is what
        decides whether the value reaches an already-persisted row (it backfills only rows that
        have none yet, and never overwrites one that does).
        """
        return [replace(item, category=classify_news_category(item)) for item in items]

    async def _persist(self, prepared: list[NewsItem]) -> list[NewsItem]:
        """Persist-then-read, degrading to the freshly-fetched items when the store is
        unreachable so a Supabase outage can't 500 `GET /api/v1/news` — the news itself
        was already fetched (issue #1 keeps `/news` as resilient as `/instruments/enriched`
        already is). Returned items keep their computed `analysis_status` but won't reflect
        a prior `AnalyzePendingNews` run's persisted status until the store recovers.
        """
        try:
            return await self._news_item_repository.upsert_many(prepared)
        except Exception:
            logger.warning(
                "News store upsert failed; serving %d freshly-fetched item(s) without persistence.",
                len(prepared),
                exc_info=True,
            )
            return prepared

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
            signal_id = await self._latest_signal_id(symbol)
            if signal_id is not None:
                latest_signal_id_by_symbol[symbol] = signal_id

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

    async def _latest_signal_id(self, symbol: str) -> str | None:
        """Newest signal id for `symbol`, or `None` if none exists — or if the signal
        store is unreachable. A transient lookup failure degrades to "no prior signal"
        (item stays `pending`) rather than failing the whole request, matching
        `ListEnrichedInstruments._latest_signal`.
        """
        try:
            existing = await self._signal_repository.list_for_instrument(symbol)
        except Exception:
            logger.warning(
                "Signal lookup failed for %s; news backfill skips it.", symbol, exc_info=True
            )
            return None
        return existing[0].id if existing else None
