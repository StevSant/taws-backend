from typing import Annotated

from fastapi import Depends

from app.application.market import NewsFeedRefresher
from app.core.di import Container, get_container


def get_news_feed_refresher(
    container: Annotated[Container, Depends(get_container)],
) -> NewsFeedRefresher:
    """FastAPI dependency resolving the process-wide NewsFeedRefresher from the DI container."""
    return container.get_news_feed_refresher()
