from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.event_intelligence.ports import NewsProviderPort


def get_event_news_provider(
    container: Annotated[Container, Depends(get_container)],
) -> NewsProviderPort:
    """FastAPI dependency resolving the cached live `NewsProviderPort` from the DI container."""
    return container.get_event_news_provider()
