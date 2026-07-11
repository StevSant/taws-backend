from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.signals.ports import SignalRepository


def get_signal_repository(
    container: Annotated[Container, Depends(get_container)],
) -> SignalRepository:
    """FastAPI dependency resolving the configured SignalRepository from the DI container."""
    return container.get_signal_repository()
