import asyncio
import logging

from app.application.market.use_cases.news_asset_impact import NewsAssetImpact
from app.application.market.use_cases.news_detail import NewsDetail
from app.application.quant import UnknownInstrumentError
from app.application.quant.use_cases import ComputeMarketStats
from app.domain.market.entities import NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository

logger = logging.getLogger(__name__)


class BuildNewsDetail:
    """Assemble everything the news-detail page renders for one article (issue #57).

    `GET /api/v1/news/{id}` used to return the bare persisted row, which left the page fetching
    its own enrichment: one `GET /quant/stats` per affected instrument plus a `GET /news?symbol=`
    for related news — N+2 round trips, and both produced nothing for the large share of
    RSS/Yahoo articles the symbol linker maps to no instrument at all. That is why the delivered
    page read as bare: the template was complete, the payload wasn't.

    This composes the enrichment server-side out of use cases and ports that already exist —
    `ComputeMarketStats` for prices (never a second price-lookup implementation),
    `NewsItemRepository.list_related` for the related list, `SignalRepository` for the Analyst's
    call — and returns it as one additive payload. No new LLM call is made: the detail view is a
    read, and paying for a classification on every page view is exactly the cost the
    `AnalyzePendingNews` gate exists to avoid.
    """

    def __init__(
        self,
        news_item_repository: NewsItemRepository,
        signal_repository: SignalRepository,
        instrument_universe: InstrumentUniverse,
        compute_market_stats: ComputeMarketStats,
        max_affected_instruments: int,
        related_news_limit: int,
        price_window_days: int,
    ) -> None:
        self._news_item_repository = news_item_repository
        self._signal_repository = signal_repository
        self._instrument_universe = instrument_universe
        self._compute_market_stats = compute_market_stats
        self._max_affected_instruments = max_affected_instruments
        self._related_news_limit = related_news_limit
        self._price_window_days = price_window_days

    async def execute(self, news_id: str) -> NewsDetail | None:
        """Return the enriched detail for `news_id`, or `None` when no such item is persisted
        (the router turns that into the same 404 it always did)."""
        item = await self._news_item_repository.get_by_id(news_id)
        if item is None:
            return None

        signal = await self._resolve_signal(item)
        symbols = item.related_symbols[: self._max_affected_instruments]
        impacts, related_news = await asyncio.gather(
            asyncio.gather(*(self._build_impact(symbol, item, signal) for symbol in symbols)),
            self._news_item_repository.list_related(item, limit=self._related_news_limit),
        )
        return NewsDetail(
            item=item,
            affected_instruments=[impact for impact in impacts if impact is not None],
            related_news=related_news,
        )

    async def _resolve_signal(self, item: NewsItem) -> Signal | None:
        """The Analyst call this article produced, if any. Fetched by id rather than by scanning
        every signal recorded for the article's instruments — `news_items.signal_id` is the FK
        that says which one is *this article's*, and the newest signal on a symbol is usually
        about some other article entirely.
        """
        if not item.signal_id:
            return None
        return await self._signal_repository.get(item.signal_id)

    async def _build_impact(
        self, symbol: str, item: NewsItem, signal: Signal | None
    ) -> NewsAssetImpact | None:
        """One affected-instrument row, or `None` for a symbol outside the curated universe
        (nothing to price it against, and no asset page for the chip to link to).
        """
        instrument = self._instrument_universe.by_symbol(symbol)
        if instrument is None:
            return None

        last_price, price_delta_pct = await self._price(instrument.symbol)
        is_target = (
            signal is not None and signal.instrument_symbol.upper() == instrument.symbol.upper()
        )
        return NewsAssetImpact(
            symbol=instrument.symbol,
            name=instrument.name,
            asset_class=instrument.asset_class,
            last_price=last_price,
            price_delta_pct=price_delta_pct,
            sentiment_score=self._sentiment_for(symbol, item),
            impact_class=signal.impact_class if signal and is_target else None,
            confidence=signal.confidence if signal and is_target else None,
            signal_id=signal.id if signal and is_target else None,
        )

    async def _price(self, symbol: str) -> tuple[float | None, float | None]:
        """Last price + window % change, or `(None, None)` on any failure.

        Best-effort by design: prices are enrichment on top of the article, so an upstream
        market-data hiccup must degrade one chip to "no price", never fail the whole page.
        """
        try:
            stats = await self._compute_market_stats.execute(symbol, self._price_window_days)
        except UnknownInstrumentError:
            return None, None
        except Exception:
            logger.warning("BuildNewsDetail: price lookup failed for %s", symbol, exc_info=True)
            return None, None
        return stats.last_price, stats.price_delta_pct

    @staticmethod
    def _sentiment_for(symbol: str, item: NewsItem) -> float | None:
        """Per-entity sentiment for this instrument when the provider scored it, else the
        article-level score. Never defaulted to `0` — "no sentiment" and "neutral" are different
        claims, and only one of them is true here.
        """
        for entity in item.entities:
            if entity.symbol.upper() == symbol.upper() and entity.sentiment_score is not None:
                return entity.sentiment_score
        return item.sentiment_score
