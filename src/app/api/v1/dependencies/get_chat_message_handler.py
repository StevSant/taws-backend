from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.telegram import ChatMessageHandler


def get_chat_message_handler(
    container: Annotated[Container, Depends(get_container)],
) -> ChatMessageHandler | None:
    """FastAPI dependency resolving the cached conversational chat handler, or `None`
    when Telegram isn't configured — same pattern as `get_briefing_command_handler`."""
    return container.get_chat_message_handler()
