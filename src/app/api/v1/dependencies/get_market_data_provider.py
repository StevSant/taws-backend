from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import MarketDataProvider


def get_market_data_provider(
    container: Annotated[Container, Depends(get_container)],
) -> MarketDataProvider:
    """FastAPI dependency resolving the configured MarketDataProvider from the DI container."""
    return container.get_market_data_provider()
