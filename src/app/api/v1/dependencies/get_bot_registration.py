from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.telegram.ports import BotRegistrationPort


async def get_bot_registration(
    container: Annotated[Container, Depends(get_container)],
) -> BotRegistrationPort:
    """DI dependency: return the cached `BotRegistrationPort` from the container."""
    return container.get_bot_registration()
