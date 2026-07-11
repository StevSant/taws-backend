from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import NewsProvider


def get_news_provider(container: Annotated[Container, Depends(get_container)]) -> NewsProvider:
    """FastAPI dependency resolving the configured NewsProvider from the DI container."""
    return container.get_news_provider()
