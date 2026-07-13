from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import CoinGeckoSearchProvider


def get_coingecko_search_provider(
    container: Annotated[Container, Depends(get_container)],
) -> CoinGeckoSearchProvider:
    """FastAPI dependency resolving the configured CoinGeckoSearchProvider from the DI container."""
    return container.get_coingecko_search_provider()
