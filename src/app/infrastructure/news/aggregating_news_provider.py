import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.errors import NewsUnavailableError
from app.domain.market.ports import InstrumentUniverse, NewsProvider
from app.infrastructure.news.dedupe_news_items import dedupe_news_items
from app.infrastructure.news.link_related_symbols import link_related_symbols

logger = logging.getLogger(__name__)


class AggregatingNewsProvider(NewsProvider):
    """NewsProvider that fans out to several configured providers concurrently.

    Merges + dedupes results (by URL/title), backfills `related_symbols` for
    items whose source didn't tag any (naive title/summary word match against
    the curated universe), restricts every item's `related_symbols`/`entities`
    to instruments actually in the curated universe (issue #10 — provider-side
    entity linkage like Marketaux's isn't scoped to our universe and otherwise
    leaks NSE/BSE/ASX/LSE tickers and index symbols with no configured adapter
    straight through to consumers), applies filters/limit, and sorts by
    `published_at` descending.

    **Real articles, an empty list, or `NewsUnavailableError` — never invented news.** This
    used to fall back to a `FixtureNewsProvider` whenever no live provider was configured or
    all of them failed, which meant an outage produced canned headlines with `example.com`
    URLs that the analyst then cited to the user as sourced reporting.

    "Every provider failed" and "no articles matched" are kept strictly apart: the first
    raises, the second returns `[]`. Collapsing them would have the agent state "there is no
    recent news on X" during an outage — a fabricated finding, just a quieter one.
    """

    def __init__(
        self,
        providers: list[NewsProvider],
        instrument_universe: InstrumentUniverse,
        provider_timeout_seconds: float = 2.5,
        live_fetch_budget_seconds: float = 3.5,
    ) -> None:
        self._providers = providers
        self._instrument_universe = instrument_universe
        self._provider_timeout_seconds = provider_timeout_seconds
        self._live_fetch_budget_seconds = live_fetch_budget_seconds

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        items = await self._collect_from_live_providers(symbols, asset_class, since_hours, limit)

        items = dedupe_news_items(items)
        items = self._backfill_related_symbols(items)
        items = self._restrict_to_universe(items)
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
        """Fan out to every provider. Raises `NewsUnavailableError` if they ALL failed.

        A provider that succeeds but has nothing to say returns `[]`; a provider that blew up
        returns `None`. Only if every single one returned `None` is this an outage — one
        surviving provider with zero matching articles is still a real, if empty, answer.
        """
        if not self._providers:
            raise NewsUnavailableError(0, "no news provider is configured")

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        self._safe_fetch(provider, symbols, asset_class, since_hours, limit)
                        for provider in self._providers
                    )
                ),
                timeout=self._live_fetch_budget_seconds,
            )
        except TimeoutError as error:
            logger.warning(
                "Live news fan-out exceeded its %.1fs budget.", self._live_fetch_budget_seconds
            )
            raise NewsUnavailableError(
                len(self._providers), f"fan-out exceeded {self._live_fetch_budget_seconds:.1f}s"
            ) from error

        if all(provider_items is None for provider_items in results):
            raise NewsUnavailableError(len(self._providers), "every provider errored or timed out")

        return [item for provider_items in results if provider_items for item in provider_items]

    async def _safe_fetch(
        self,
        provider: NewsProvider,
        symbols: list[str] | None,
        asset_class: AssetClass | None,
        since_hours: int,
        limit: int,
    ) -> list[NewsItem] | None:
        """The provider's articles, or `None` if it failed. `[]` means "succeeded, found none"."""
        try:
            return await asyncio.wait_for(
                provider.fetch_news(
                    symbols=symbols, asset_class=asset_class, since_hours=since_hours, limit=limit
                ),
                timeout=self._provider_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "NewsProvider %s timed out after %.1fs; skipping it.",
                type(provider).__name__,
                self._provider_timeout_seconds,
            )
            return None
        except Exception:
            logger.warning(
                "NewsProvider %s failed; skipping it.", type(provider).__name__, exc_info=True
            )
            return None

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

    def _restrict_to_universe(self, items: list[NewsItem]) -> list[NewsItem]:
        """Drop any `related_symbols`/`entities` not covered by the curated universe.

        Provider-side entity linkage (e.g. `MarketauxNewsProvider`) tags articles with
        that vendor's own global instrument identifiers, which cover far more than our
        curated `InstrumentUniverse` — Indian NSE/BSE indices, ASX/LSE tickers, etc.
        `_backfill_related_symbols` above only fills in symbols when a source provides
        none; it never validates symbols a source *did* provide. Left unfiltered, those
        out-of-universe symbols flow straight through `GET /api/v1/news` to callers
        (the radar UI, `GenerateSignal`, scenario synthesis), which then request
        `/quant/stats` for instruments no adapter can ever serve (issue #10).
        """
        restricted = []
        for item in items:
            known_symbols = [s for s in item.related_symbols if self._is_known_symbol(s)]
            known_entities = [e for e in item.entities if self._is_known_symbol(e.symbol)]
            if known_symbols == item.related_symbols and known_entities == item.entities:
                restricted.append(item)
            else:
                new_item = replace(item, related_symbols=known_symbols, entities=known_entities)
                restricted.append(new_item)
        return restricted

    def _is_known_symbol(self, symbol: str) -> bool:
        return self._instrument_universe.by_symbol(symbol) is not None

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
