import asyncio
from datetime import UTC, datetime
from time import mktime
from typing import Any

import feedparser

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider


class RssNewsProvider(NewsProvider):
    """NewsProvider adapter that parses configured RSS feeds via `feedparser`.

    `feedparser` is synchronous, so each feed fetch/parse runs in a worker thread
    via `asyncio.to_thread`; feeds are fetched concurrently and a failure on one
    feed never drops the others. Returns items with empty `related_symbols` —
    linking is done centrally by `AggregatingNewsProvider`.
    """

    def __init__(self, feed_urls: list[str]) -> None:
        self._feed_urls = feed_urls

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        del (
            symbols,
            asset_class,
        )  # RSS has no query filters; filtering done centrally in the aggregator
        if not self._feed_urls:
            return []

        results = await asyncio.gather(
            *(asyncio.to_thread(feedparser.parse, url) for url in self._feed_urls),
            return_exceptions=True,
        )

        items: list[NewsItem] = []
        for feed_url, result in zip(self._feed_urls, results, strict=True):
            if isinstance(result, BaseException):
                continue
            items.extend(self._to_news_items(result, feed_url))

        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:limit]

    @staticmethod
    def _to_news_items(feed: Any, feed_url: str) -> list[NewsItem]:
        source_name = (feed.feed or {}).get("title") or feed_url
        items: list[NewsItem] = []
        for entry in feed.get("entries", []):
            published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            published_at = (
                datetime.fromtimestamp(mktime(published_struct), tz=UTC)
                if published_struct
                else datetime.now(UTC)
            )
            items.append(
                NewsItem(
                    id=entry.get("id") or entry.get("link") or "",
                    title=entry.get("title") or "",
                    summary=entry.get("summary") or "",
                    url=entry.get("link") or "",
                    source=source_name,
                    published_at=published_at,
                    related_symbols=[],
                )
            )
        return items
