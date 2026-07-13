from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository


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
        self, asset_symbol: str | None = None, news_id: str | None = None
    ) -> str | None:
        if asset_symbol:
            instrument = self._instrument_universe.by_symbol(asset_symbol)
            return _format_instrument(instrument) if instrument else None
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
