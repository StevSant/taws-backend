import asyncio
import logging
from datetime import UTC, datetime
from time import mktime
from typing import Any

import feedparser

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider
from app.infrastructure.news.extract_rss_image_url import extract_rss_image_url
from app.infrastructure.news.extract_rss_summary import extract_rss_summary

logger = logging.getLogger(__name__)


class RssNewsProvider(NewsProvider):
    """NewsProvider adapter that parses configured RSS feeds via `feedparser`.

    `feedparser` is synchronous, so each feed fetch/parse runs in a worker thread via
    `asyncio.to_thread`, bounded by `timeout_seconds` (configured via
    `Settings.rss_feed_timeout_seconds`) — some feeds (e.g. Yahoo Finance's RSS
    endpoint) stall the connection instead of erroring, and `feedparser.parse` has no
    timeout of its own, so left unbounded, one stuck feed hangs the whole `fetch_news`
    call. `asyncio.wait_for` turns that hang into a `TimeoutError`, which
    `asyncio.gather(..., return_exceptions=True)` already treats as "this feed
    returned nothing" for this fetch. Feeds are fetched concurrently and a failure (or
    timeout) on one feed never drops the others. Returns items with empty
    `related_symbols` — linking is done centrally by `AggregatingNewsProvider`.
    """

    def __init__(self, feed_urls: list[str], timeout_seconds: float) -> None:
        self._feed_urls = feed_urls
        self._timeout_seconds = timeout_seconds

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
            *(
                asyncio.wait_for(
                    asyncio.to_thread(feedparser.parse, url),
                    timeout=self._timeout_seconds,
                )
                for url in self._feed_urls
            ),
            return_exceptions=True,
        )

        items: list[NewsItem] = []
        for feed_url, result in zip(self._feed_urls, results, strict=True):
            if isinstance(result, TimeoutError):
                logger.warning(
                    "RSS feed %s timed out after %.0fs; treating it as empty for this fetch.",
                    feed_url,
                    self._timeout_seconds,
                )
                continue
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
                    summary=extract_rss_summary(entry),
                    url=entry.get("link") or "",
                    source=source_name,
                    provider="rss",
                    published_at=published_at,
                    related_symbols=[],
                    image_url=extract_rss_image_url(entry),
                )
            )
        return items
