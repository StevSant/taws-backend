from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.watchlist.ports import WatchlistRepository


def get_watchlist_repository(
    container: Annotated[Container, Depends(get_container)],
) -> WatchlistRepository:
    """FastAPI dependency resolving the configured WatchlistRepository from the DI container."""
    return container.get_watchlist_repository()
