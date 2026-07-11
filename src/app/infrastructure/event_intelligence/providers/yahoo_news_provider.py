from app.domain.event_intelligence.entities import NewsEvent
from app.domain.event_intelligence.ports import NewsProviderPort

_NOT_IMPLEMENTED_MESSAGE = (
    "YahooNewsProvider is a stub for future implementation. "
    "Implement to fetch real news from Yahoo Finance."
)


class YahooNewsProvider(NewsProviderPort):
    """Stub for a future Yahoo Finance news provider.

    Not implemented yet. When ready, this will fetch financial news
    from Yahoo Finance and return `NewsEvent` objects.
    """

    def __init__(self) -> None:
        pass

    async def fetch_latest_news(self) -> list[NewsEvent]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)
