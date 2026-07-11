from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.telegram.ports import TelegramLinkTokenRepository


def get_telegram_link_token_repository(
    container: Annotated[Container, Depends(get_container)],
) -> TelegramLinkTokenRepository:
    """FastAPI dependency resolving the configured TelegramLinkTokenRepository from the
    DI container."""
    return container.get_telegram_link_token_repository()
