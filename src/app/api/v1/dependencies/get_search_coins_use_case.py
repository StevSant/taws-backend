from typing import Annotated

from fastapi import Depends

from app.application.instruments.use_cases import SearchCoins
from app.core.di import Container, get_container


def get_search_coins_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> SearchCoins:
    """FastAPI dependency resolving the cached SearchCoins use case from the DI container."""
    return container.get_search_coins_use_case()
