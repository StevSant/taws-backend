import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider


class FinnhubNewsProvider(NewsProvider):
    """NewsProvider adapter backed by Finnhub's `/company-news` endpoint.

    Finnhub's company-news is per-symbol, so this adapter only returns results
    when `symbols` is provided — general/no-symbol queries are covered by the
    other configured providers (NewsAPI, RSS, Marketaux). Without an API key it
    returns no items instead of crashing.
    """

    def __init__(self, api_key: str | None, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        del asset_class  # per-symbol source; asset-class filtering done centrally in the aggregator
        if not self._api_key or not symbols:
            return []

        since_date = (datetime.now(UTC) - timedelta(hours=since_hours)).date()
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            results = await asyncio.gather(
                *(self._fetch_symbol(client, symbol, since_date) for symbol in symbols),
                return_exceptions=True,
            )

        items: list[NewsItem] = []
        for result in results:
            if isinstance(result, BaseException):
                continue
            items.extend(result)
        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:limit]

    async def _fetch_symbol(
        self, client: httpx.AsyncClient, symbol: str, since_date: date
    ) -> list[NewsItem]:
        response = await client.get(
            "/company-news",
            params={
                "symbol": symbol,
                "from": since_date.isoformat(),
                "to": date.today().isoformat(),
                "token": self._api_key or "",
            },
        )
        response.raise_for_status()
        payload = response.json()

        items: list[NewsItem] = []
        for entry in payload:
            item = self._to_news_item(entry, symbol)
            if item is not None:
                items.append(item)
        return items

    @staticmethod
    def _to_news_item(entry: dict, symbol: str) -> NewsItem | None:
        try:
            return NewsItem(
                id=str(entry["id"]),
                title=entry.get("headline") or "",
                summary=entry.get("summary") or "",
                url=entry.get("url") or "",
                source=entry.get("source") or "Finnhub",
                published_at=datetime.fromtimestamp(entry["datetime"], tz=UTC),
                related_symbols=[symbol],
            )
        except (KeyError, ValueError, TypeError):
            return None
