from abc import ABC, abstractmethod

from app.domain.market.entities import AssetClass, NewsItem


class NewsProvider(ABC):
    """Port for fetching news, optionally scoped to instruments/asset class.

    Adapters: Marketaux (entity + sentiment enrichment), NewsAPI.org, Finnhub,
    RSS feeds, a fixture fallback, and an `AggregatingNewsProvider` that fans
    out to several of the above. Every returned `NewsItem` must carry `source`
    and `published_at` (HU1 criteria).
    """

    @abstractmethod
    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        """Return recent news, most-recent first, filtered by the given criteria."""
        raise NotImplementedError
