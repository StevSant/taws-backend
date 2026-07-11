from abc import ABC, abstractmethod

from app.domain.chat.entities import Conversation


class ConversationRepository(ABC):
    """Port for persisting and retrieving conversations."""

    @abstractmethod
    async def get(self, conversation_id: str) -> Conversation | None:
        """Return the conversation with this id, or `None` if it doesn't exist."""
        raise NotImplementedError

    @abstractmethod
    async def save(self, conversation: Conversation) -> None:
        """Create or update a conversation."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[Conversation]:
        """Return all conversations belonging to `user_id`."""
        raise NotImplementedError
