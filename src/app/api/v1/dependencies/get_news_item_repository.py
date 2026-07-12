from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import NewsItemRepository


def get_news_item_repository(
    container: Annotated[Container, Depends(get_container)],
) -> NewsItemRepository:
    """FastAPI dependency resolving the configured NewsItemRepository from the DI container."""
    return container.get_news_item_repository()
