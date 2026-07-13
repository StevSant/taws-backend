from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.event_intelligence.ports import EventRepositoryPort


def get_event_repository(
    container: Annotated[Container, Depends(get_container)],
) -> EventRepositoryPort:
    """FastAPI dependency resolving the configured EventRepositoryPort from the DI container."""
    return container.get_event_repository()
