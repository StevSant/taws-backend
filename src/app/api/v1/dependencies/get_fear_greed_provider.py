from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.sentiment.ports import FearGreedProvider


def get_fear_greed_provider(
    container: Annotated[Container, Depends(get_container)],
) -> FearGreedProvider:
    """FastAPI dependency resolving the configured FearGreedProvider from the DI container."""
    return container.get_fear_greed_provider()
