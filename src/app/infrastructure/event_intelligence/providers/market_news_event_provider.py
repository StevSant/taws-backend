from app.domain.event_intelligence.entities import NewsEvent
from app.domain.event_intelligence.ports import NewsProviderPort
from app.domain.market.entities import NewsItem
from app.domain.market.ports import NewsProvider


class MarketNewsEventProvider(NewsProviderPort):
    """Feeds the Event Intelligence (Sentinel/Gemini) pipeline from the REAL news providers.

    The bridge between this codebase's two, previously unconnected, news worlds:

    - `domain.market.ports.NewsProvider` — the live, battle-tested ingestion side
      (Marketaux, NewsAPI, Finnhub, RSS, SEC EDGAR, fanned out and deduped by
      `AggregatingNewsProvider`, which itself falls back to fixtures when nothing is
      configured). Yields `NewsItem`.
    - `domain.event_intelligence.ports.NewsProviderPort` — what the Gemini analyzer consumes.
      Yields `NewsEvent`.

    The Sentinel pipeline's only wired adapter used to be `DemoNewsProvider` — ~43 hardcoded
    articles with fake `example.com` URLs — and the one alternative (`YahooNewsProvider`) is a
    stub that raises `NotImplementedError`. So Gemini only ever analyzed canned demo text and no
    live headline could reach a Telegram alert. This adapter is what makes the scheduled Sentinel
    scan (`BroadcastImportantEvents`) analyze actual market news.

    Deliberately a thin mapper, not a second ingestion stack: reusing `NewsProvider` inherits
    its rate limiting, circuit breakers, dedup and fixture fallback for free rather than
    reimplementing five upstream clients behind a different port.
    """

    def __init__(self, news_provider: NewsProvider, since_hours: int, limit: int) -> None:
        self._news_provider = news_provider
        self._since_hours = since_hours
        self._limit = limit

    async def fetch_latest_news(self) -> list[NewsEvent]:
        items = await self._news_provider.fetch_news(
            since_hours=self._since_hours, limit=self._limit
        )
        return [_to_event(item) for item in items]


def _to_event(item: NewsItem) -> NewsEvent:
    """Map a `NewsItem` onto the `NewsEvent` the analyzer expects.

    `description` and `content` both take the summary: upstream `NewsItem`s carry no separate
    full-text body (none of the free-tier providers return one), and Gemini's prompt reads both
    fields. Passing the summary twice is honest — it is genuinely all the text there is — and
    beats sending an empty `content`, which reads to the model as "this article has no body".
    """
    return NewsEvent(
        title=item.title,
        description=item.summary,
        content=item.summary,
        source=item.source,
        url=item.url,
        published_at=item.published_at,
    )
