from typing import Annotated

from fastapi import Depends

from app.application.chat.use_cases import GenerateConversationTitle
from app.core.di import Container, get_container


def get_generate_conversation_title_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> GenerateConversationTitle:
    """FastAPI dependency resolving the conversation-title generator from the container."""
    return container.get_generate_conversation_title_use_case()
