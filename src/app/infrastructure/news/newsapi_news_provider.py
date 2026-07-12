from datetime import datetime

import httpx

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider


class NewsApiNewsProvider(NewsProvider):
    """NewsProvider adapter backed by the NewsAPI.org `/everything` endpoint.

    Returns items with empty `related_symbols` — NewsAPI doesn't tag instruments
    itself, so linking is done centrally by `AggregatingNewsProvider`. Without an
    API key it returns no items instead of crashing.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        default_query: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._default_query = default_query
        self._timeout_seconds = timeout_seconds

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        del asset_class  # NewsAPI has no asset-class filter; done centrally in the aggregator
        if not self._api_key:
            return []

        query = " OR ".join(symbols) if symbols else self._default_query
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": min(limit, 100),
            "apiKey": self._api_key,
        }
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            response = await client.get("/everything", params=params)
            response.raise_for_status()
            payload = response.json()

        items: list[NewsItem] = []
        for article in payload.get("articles", []):
            item = self._to_news_item(article)
            if item is not None:
                items.append(item)
        return items[:limit]

    @staticmethod
    def _to_news_item(article: dict) -> NewsItem | None:
        try:
            source = article.get("source") or {}
            published_raw = article.get("publishedAt") or ""
            return NewsItem(
                id=article.get("url") or "",
                title=article.get("title") or "",
                summary=article.get("description") or "",
                url=article.get("url") or "",
                source=source.get("name") or "NewsAPI",
                provider="newsapi",
                published_at=datetime.fromisoformat(published_raw.replace("Z", "+00:00")),
                related_symbols=[],
            )
        except (KeyError, ValueError, TypeError):
            return None
