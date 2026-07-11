from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import VectorStore


def get_vector_store(container: Annotated[Container, Depends(get_container)]) -> VectorStore:
    """FastAPI dependency resolving the configured VectorStore from the DI container."""
    return container.get_vector_store()
