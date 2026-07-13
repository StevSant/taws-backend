import logging
from dataclasses import replace

from app.application.market.use_cases.ingest_news import IngestNews
from app.domain.market.entities import AssetClass, NewsBrowseQuery, PaginatedNewsItems
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository

logger = logging.getLogger(__name__)


class BrowseNews:
    """DB-backed, paginated/sortable/filterable news listing (`GET /api/v1/news/browse`, issue #70).

    Reads the persisted `news_items` store only — it never blocks on upstream providers, which
    is what lets it report an exact `total` and sort globally instead of within whatever slice a
    provider returned.

    Nothing ingests news on a schedule, though: the store is filled by the live
    `GET /api/v1/news` feed, so a pure DB read would slowly go stale. To stay fresh without an
    upstream fetch on every page click, this fires a best-effort `IngestNews` refresh **on page 1
    only**. A failed refresh is logged and swallowed — the DB read still serves — matching the
    Supabase-outage degradation `IngestNews` already does internally.
    """

    def __init__(
        self,
        news_item_repository: NewsItemRepository,
        instrument_universe: InstrumentUniverse,
        ingest_news: IngestNews,
    ) -> None:
        self._repository = news_item_repository
        self._universe = instrument_universe
        self._ingest_news = ingest_news

    async def execute(
        self,
        query: NewsBrowseQuery,
        asset_class: AssetClass | None = None,
    ) -> PaginatedNewsItems:
        resolved = self._resolve_symbols(query, asset_class)
        if resolved.page == 1:
            await self._refresh_first_page(resolved, asset_class)
        return await self._repository.browse(resolved)

    def _resolve_symbols(
        self, query: NewsBrowseQuery, asset_class: AssetClass | None
    ) -> NewsBrowseQuery:
        """Expand an `asset_class` filter into its member symbols, so the repository only ever
        sees concrete symbols and stays ignorant of the instrument universe.

        An explicit symbol wins: asset class only applies when the caller didn't name one (a
        symbol is always a subset of exactly one class, so intersecting them would be a no-op
        at best and an empty set at worst).
        """
        if query.symbols or asset_class is None:
            return query
        members = [instrument.symbol for instrument in self._universe.by_asset_class(asset_class)]
        return replace(query, symbols=members or None)

    async def _refresh_first_page(
        self, query: NewsBrowseQuery, asset_class: AssetClass | None
    ) -> None:
        try:
            await self._ingest_news.execute(
                symbols=query.symbols,
                asset_class=asset_class,
                since_hours=query.since_hours,
                limit=query.page_size,
            )
        except Exception:
            logger.warning(
                "News browse page-1 refresh failed; serving the persisted store as-is.",
                exc_info=True,
            )
