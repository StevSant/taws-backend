from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.telegram.ports import UserBotRepository


async def get_user_bot_repository(
    container: Annotated[Container, Depends(get_container)],
) -> UserBotRepository:
    """DI dependency: return the cached `UserBotRepository` from the container."""
    return container.get_user_bot_repository()
