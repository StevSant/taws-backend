from abc import ABC, abstractmethod

from app.domain.event_intelligence.entities import NewsEvent


class NewsProviderPort(ABC):
    """Port for fetching raw news events from an external source.

    Implementations (DemoNewsProvider, YahooNewsProvider, ...) connect to
    a specific news API or fixture and return `NewsEvent` objects.
    """

    @abstractmethod
    async def fetch_latest_news(self) -> list[NewsEvent]:
        """Fetch the latest news events from the source."""
        raise NotImplementedError
