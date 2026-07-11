from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.chat.ports import ConversationRepository


def get_conversation_repository(
    container: Annotated[Container, Depends(get_container)],
) -> ConversationRepository:
    """FastAPI dependency resolving the configured ConversationRepository from the DI container."""
    return container.get_conversation_repository()
