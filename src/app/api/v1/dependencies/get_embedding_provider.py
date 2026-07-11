from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import EmbeddingProvider


def get_embedding_provider(
    container: Annotated[Container, Depends(get_container)],
) -> EmbeddingProvider:
    """FastAPI dependency resolving the configured EmbeddingProvider from the DI container."""
    return container.get_embedding_provider()
