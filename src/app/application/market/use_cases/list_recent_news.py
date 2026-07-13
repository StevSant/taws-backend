import logging

from app.application.market.use_cases.ingest_news import IngestNews
from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository

logger = logging.getLogger(__name__)


class ListRecentNews:
    """DB-first read path behind `GET /api/v1/news` (taws#71).

    `IngestNews` — the previous handler for this endpoint — re-aggregates the upstream
    feeds (Yahoo / RSS / Finnhub) and persist-then-reads them *synchronously, on the
    request path*. On a cold provider cache that regularly overshot the radar client's
    20s request timeout, and the radar page died with a full-page "Timeout has occurred"
    banner. But every article the pipeline ever fetched is already persisted in
    `news_items`, so the response can be served straight out of the store.

    This use case does exactly that: read the persisted window and return. Keeping the
    store warm is somebody else's job — `NewsFeedRefresher` runs `IngestNews` out-of-band,
    after the response has already been flushed.

    Two escape hatches, both config-driven:

    - **Cold store.** If the store holds fewer than `min_persisted_items` rows for the
      requested window (a brand-new database, or a symbol nobody has ever queried), fall
      back to running `IngestNews` inline — otherwise the very first caller would get an
      empty feed and no amount of background refreshing would help them *now*. Set
      `min_persisted_items` to 1 (the default) to take this path only on a truly empty read.
    - **Kill switch.** `db_first_enabled=False` restores the old always-blocking behavior.

    The response contract is unchanged: same `NewsItem`s, same ordering (newest first),
    same filters.
    """

    def __init__(
        self,
        news_item_repository: NewsItemRepository,
        instrument_universe: InstrumentUniverse,
        ingest_news: IngestNews,
        db_first_enabled: bool = True,
        min_persisted_items: int = 1,
    ) -> None:
        self._news_item_repository = news_item_repository
        self._instrument_universe = instrument_universe
        self._ingest_news = ingest_news
        self._db_first_enabled = db_first_enabled
        self._min_persisted_items = min_persisted_items

    async def execute(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        if not self._db_first_enabled:
            return await self._fetch_upstream(symbols, asset_class, since_hours, limit)

        filter_symbols = self._resolve_filter_symbols(symbols, asset_class)
        if filter_symbols is not None and not filter_symbols:
            # A filter no instrument in the curated universe can satisfy: an unknown symbol,
            # or an asset class with no instruments. Nothing can ever match it — upstream
            # included, since `AggregatingNewsProvider` restricts every item to the universe
            # — so answer empty instead of paying for a fan-out that returns nothing.
            return []

        persisted = await self._read_persisted(filter_symbols, since_hours, limit)
        if persisted is not None and len(persisted) >= self._min_persisted_items:
            return persisted

        return await self._fetch_upstream(symbols, asset_class, since_hours, limit)

    async def _read_persisted(
        self, filter_symbols: list[str] | None, since_hours: int, limit: int
    ) -> list[NewsItem] | None:
        """The persisted window, or `None` when the store is unreachable — which the caller
        treats exactly like a cold store: degrade to the upstream fetch rather than 500.
        """
        try:
            return await self._news_item_repository.list_recent(
                symbols=filter_symbols, since_hours=since_hours, limit=limit
            )
        except Exception:
            logger.warning(
                "Persisted news read failed; falling back to a live upstream fetch.",
                exc_info=True,
            )
            return None

    def _resolve_filter_symbols(
        self, symbols: list[str] | None, asset_class: AssetClass | None
    ) -> list[str] | None:
        """Collapse the `symbol` + `asset_class` query filters into the exact set of
        universe symbols a persisted item must be linked to, or `None` for "no filter".

        `news_items` has no `asset_class` column — an article's asset class is implied by
        the instruments in its `related_symbols`. Expanding the class into its symbols here
        keeps the filtering in the DB query (exact, one round-trip) instead of over-fetching
        and re-filtering rows in Python.
        """
        requested = self._canonical_symbols(symbols) if symbols else None
        if asset_class is None:
            return requested

        in_class = [
            instrument.symbol
            for instrument in self._instrument_universe.by_asset_class(asset_class)
        ]
        if requested is None:
            return in_class
        in_class_set = set(in_class)
        return [symbol for symbol in requested if symbol in in_class_set]

    def _canonical_symbols(self, symbols: list[str]) -> list[str]:
        """Map requested symbols onto their curated-universe spelling, dropping unknown ones.

        `related_symbols` is only ever written with universe symbols (`AggregatingNewsProvider`
        restricts every item to the curated universe), so matching on the canonical spelling
        is what makes the DB `overlaps` filter case-insensitive in practice.
        """
        resolved = []
        for symbol in symbols:
            instrument = self._instrument_universe.by_symbol(symbol)
            if instrument is not None:
                resolved.append(instrument.symbol)
        return resolved

    async def _fetch_upstream(
        self,
        symbols: list[str] | None,
        asset_class: AssetClass | None,
        since_hours: int,
        limit: int,
    ) -> list[NewsItem]:
        return await self._ingest_news.execute(
            symbols=symbols, asset_class=asset_class, since_hours=since_hours, limit=limit
        )
