from datetime import date

from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository

_WINDOW_NEWS_LIMIT = 12


class ResolveGroundingContext:
    """Resolves an optional chat reference (asset symbol OR news id) to a grounding string.

    Grounds a chat answer on one specific market asset or news article (issue #73).
    Depends only on the domain `InstrumentUniverse` / `NewsItemRepository` ports, so the
    application layer stays free of any vendor/framework import. At most one reference is
    expected; when both are given, `asset_symbol` wins. An unset or unresolvable reference
    yields `None`, so callers behave exactly as before (no grounding).
    """

    def __init__(
        self,
        instrument_universe: InstrumentUniverse,
        news_item_repository: NewsItemRepository,
    ) -> None:
        self._instrument_universe = instrument_universe
        self._news_item_repository = news_item_repository

    async def execute(
        self,
        asset_symbol: str | None = None,
        news_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> str | None:
        if asset_symbol:
            instrument = self._instrument_universe.by_symbol(asset_symbol)
            if not instrument:
                return None
            if from_date and to_date:
                news = await self._news_item_repository.list_for_symbol_in_range(
                    asset_symbol, from_date, to_date, _WINDOW_NEWS_LIMIT
                )
                return _format_instrument_window(instrument, from_date, to_date, news)
            return _format_instrument(instrument)
        if news_id:
            news_item = await self._news_item_repository.get_by_id(news_id)
            return _format_news_item(news_item) if news_item else None
        return None


def _format_instrument(instrument: Instrument) -> str:
    return (
        "The user is asking about this specific asset. Ground your answer on it:\n"
        f"- Symbol: {instrument.symbol}\n"
        f"- Name: {instrument.name}\n"
        f"- Asset class: {instrument.asset_class.value}\n"
        f"- Currency: {instrument.currency}"
    )


def _format_news_item(news_item: NewsItem) -> str:
    return (
        "The user is asking about this specific news article. Ground your answer on it:\n"
        f"- Title: {news_item.title}\n"
        f"- Source: {news_item.source}\n"
        f"- Published: {news_item.published_at.isoformat()}\n"
        f"- Summary: {news_item.summary}\n"
        f"- URL: {news_item.url}"
    )


def _format_instrument_window(
    instrument: Instrument, from_date: date, to_date: date, news: list[NewsItem]
) -> str:
    header = (
        "The user selected a date window on this asset's price chart and is asking WHY the "
        "price moved during it. Explain the likely drivers using ONLY the news below from that "
        "window; if the news is thin or unrelated, say so plainly instead of inventing causes.\n"
        f"- Symbol: {instrument.symbol}\n"
        f"- Name: {instrument.name}\n"
        f"- Window: {from_date.isoformat()} to {to_date.isoformat()}"
    )
    if not news:
        return f"{header}\n- News in window: none found for this asset in this period."
    lines = "\n".join(
        f"  - [{item.published_at.date().isoformat()}] {item.title} ({item.source})"
        for item in news
    )
    return f"{header}\n- News in window (most recent first):\n{lines}"
