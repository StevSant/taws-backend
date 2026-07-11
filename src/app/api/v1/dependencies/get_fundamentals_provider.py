from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import FundamentalsProvider


def get_fundamentals_provider(
    container: Annotated[Container, Depends(get_container)],
) -> FundamentalsProvider:
    """FastAPI dependency resolving the configured FundamentalsProvider from the DI container."""
    return container.get_fundamentals_provider()
