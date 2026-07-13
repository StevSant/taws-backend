from abc import ABC, abstractmethod

from app.domain.event_intelligence.entities import NewsEvent


class NewsProviderPort(ABC):
    """Port for fetching raw news events from an external source.

    Implementations (MarketNewsEventProvider, YahooNewsProvider, ...) connect to a real
    news API and return `NewsEvent` objects. An implementation must never return invented
    articles: the events it yields are analyzed and broadcast to users as market reporting.
    """

    @abstractmethod
    async def fetch_latest_news(self) -> list[NewsEvent]:
        """Fetch the latest news events from the source."""
        raise NotImplementedError
