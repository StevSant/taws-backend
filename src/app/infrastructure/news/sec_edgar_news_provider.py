import asyncio
import re
from datetime import UTC, datetime
from time import mktime
from typing import Any

import feedparser

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider

_SOURCE_NAME = "SEC EDGAR"
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


class SecEdgarNewsProvider(NewsProvider):
    """NewsProvider adapter that parses SEC EDGAR's "latest filings" Atom feed(s) — e.g. new
    8-K (material event) filings — surfacing them as a news-like feed input to the Analyst
    pipeline (issue #21's "8-K just dropped").

    Same shape as `RssNewsProvider` (`feedparser`, offloaded to a worker thread via
    `asyncio.to_thread`, feeds fetched concurrently, one feed's failure never drops the
    others) with one required addition: every request sends a descriptive `User-Agent`
    header, per SEC's fair-access policy
    (https://www.sec.gov/os/webmaster-faq#developers) — EDGAR requires a User-Agent
    identifying the requester (e.g. `"<App/Company Name> <contact email>"`) and may
    block/throttle requests without one. `user_agent` comes from
    `Settings.sec_edgar_user_agent`, never hardcoded here.

    `feed_urls` are pre-built full EDGAR "current events" feed URLs (e.g. filtered to
    `type=8-K`), configured via `Settings.sec_edgar_feed_urls` — same "pre-built URL
    list in Settings" shape as `Settings.rss_feed_urls`, so adding another form type or
    filter is a config change, not a code change.

    Returns items with empty `related_symbols`: EDGAR's feed identifies filers by company
    name + CIK, not ticker, so linking is done centrally by `AggregatingNewsProvider`
    (naive company-name word match against the curated universe), same as `RssNewsProvider`.
    """

    def __init__(self, feed_urls: list[str], user_agent: str) -> None:
        self._feed_urls = feed_urls
        self._user_agent = user_agent

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
        )  # EDGAR's feed has no query filters; filtering done centrally in the aggregator
        if not self._feed_urls:
            return []

        results = await asyncio.gather(
            *(asyncio.to_thread(self._parse_feed, url) for url in self._feed_urls),
            return_exceptions=True,
        )

        items: list[NewsItem] = []
        for result in results:
            if isinstance(result, BaseException):
                continue
            items.extend(self._to_news_items(result))

        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:limit]

    def _parse_feed(self, url: str) -> Any:
        # `agent` sets the User-Agent feedparser itself would otherwise default to a
        # generic string for; `request_headers` additionally forces it onto the actual
        # HTTP request feedparser issues — belt-and-suspenders so EDGAR always sees the
        # required identifying header regardless of feedparser's internal HTTP path.
        return feedparser.parse(
            url, agent=self._user_agent, request_headers={"User-Agent": self._user_agent}
        )

    @staticmethod
    def _to_news_items(feed: Any) -> list[NewsItem]:
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
                    summary=_strip_html_tags(entry.get("summary") or ""),
                    url=entry.get("link") or "",
                    source=_SOURCE_NAME,
                    published_at=published_at,
                    related_symbols=[],
                )
            )
        return items


def _strip_html_tags(text: str) -> str:
    """Strip EDGAR's inline HTML tags (e.g. `<b>Filed:</b>`, `<br/>`) from a summary,
    collapsing the result to plain whitespace-separated text — EDGAR's Atom `summary`
    field is `type="html"`, unlike the plain-text summaries `RssNewsProvider`'s sources
    typically provide.
    """
    return " ".join(_HTML_TAG_PATTERN.sub(" ", text).split())
