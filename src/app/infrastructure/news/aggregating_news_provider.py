import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsProvider
from app.infrastructure.news.dedupe_news_items import dedupe_news_items
from app.infrastructure.news.link_related_symbols import link_related_symbols

logger = logging.getLogger(__name__)


class AggregatingNewsProvider(NewsProvider):
    """NewsProvider that fans out to several configured providers concurrently.

    Merges + dedupes results (by URL/title), backfills `related_symbols` for
    items whose source didn't tag any (naive title/summary word match against
    the curated universe), applies filters/limit, and sorts by `published_at`
    descending. Falls back to the fixture provider whenever no live provider is
    configured, or every one of them fails or returns nothing.
    """

    def __init__(
        self,
        providers: list[NewsProvider],
        fixture_provider: NewsProvider,
        instrument_universe: InstrumentUniverse,
    ) -> None:
        self._providers = providers
        self._fixture_provider = fixture_provider
        self._instrument_universe = instrument_universe

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        items = await self._collect_from_live_providers(symbols, asset_class, since_hours, limit)
        if not items:
            items = await self._safe_fetch(
                self._fixture_provider, symbols, asset_class, since_hours, limit
            )

        items = dedupe_news_items(items)
        items = self._backfill_related_symbols(items)
        items = [item for item in items if self._matches(item, symbols, asset_class, since_hours)]
        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:limit]

    async def _collect_from_live_providers(
        self,
        symbols: list[str] | None,
        asset_class: AssetClass | None,
        since_hours: int,
        limit: int,
    ) -> list[NewsItem]:
        if not self._providers:
            return []

        results = await asyncio.gather(
            *(
                self._safe_fetch(provider, symbols, asset_class, since_hours, limit)
                for provider in self._providers
            )
        )
        return [item for provider_items in results for item in provider_items]

    @staticmethod
    async def _safe_fetch(
        provider: NewsProvider,
        symbols: list[str] | None,
        asset_class: AssetClass | None,
        since_hours: int,
        limit: int,
    ) -> list[NewsItem]:
        try:
            return await provider.fetch_news(
                symbols=symbols, asset_class=asset_class, since_hours=since_hours, limit=limit
            )
        except Exception:
            logger.warning(
                "NewsProvider %s failed; skipping it.", type(provider).__name__, exc_info=True
            )
            return []

    def _backfill_related_symbols(self, items: list[NewsItem]) -> list[NewsItem]:
        instruments = self._instrument_universe.all()
        backfilled = []
        for item in items:
            if item.related_symbols:
                backfilled.append(item)
                continue
            matched = link_related_symbols(f"{item.title} {item.summary}", instruments)
            backfilled.append(replace(item, related_symbols=matched) if matched else item)
        return backfilled

    def _matches(
        self,
        item: NewsItem,
        symbols: list[str] | None,
        asset_class: AssetClass | None,
        since_hours: int,
    ) -> bool:
        if datetime.now(UTC) - item.published_at > timedelta(hours=since_hours):
            return False

        item_symbols = {symbol.upper() for symbol in item.related_symbols}

        if symbols and not ({symbol.upper() for symbol in symbols} & item_symbols):
            return False

        return not asset_class or any(
            (instrument := self._instrument_universe.by_symbol(symbol))
            and instrument.asset_class == asset_class
            for symbol in item_symbols
        )
