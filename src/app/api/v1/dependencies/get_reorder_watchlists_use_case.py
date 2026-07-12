from typing import Annotated

from fastapi import Depends

from app.application.watchlist.use_cases import ReorderWatchlists
from app.core.di import Container, get_container


def get_reorder_watchlists_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> ReorderWatchlists:
    """FastAPI dependency resolving the cached `ReorderWatchlists` use case (issue #66)."""
    return container.get_reorder_watchlists_use_case()
