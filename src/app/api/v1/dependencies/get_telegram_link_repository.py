from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.telegram.ports import TelegramLinkRepository


def get_telegram_link_repository(
    container: Annotated[Container, Depends(get_container)],
) -> TelegramLinkRepository:
    """FastAPI dependency resolving the configured TelegramLinkRepository from the DI container."""
    return container.get_telegram_link_repository()
