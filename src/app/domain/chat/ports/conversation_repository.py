from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.domain.agents.entities import Message
from app.domain.chat.entities import Conversation


class ConversationRepository(ABC):
    """Port for persisting and retrieving conversations.

    Ownership is NOT enforced here. The backend talks to Supabase with the service-role
    key, which bypasses RLS, so the `auth.uid()` policies on `conversations` only guard
    direct client access. Every caller that resolves a conversation on behalf of a user
    must check `conversation.user_id` itself — see `chat.py`'s `_get_owned_conversation`,
    the same shape as `notes.py`'s `_get_owned_note`.
    """

    @abstractmethod
    async def get(self, conversation_id: str) -> Conversation | None:
        """Return the conversation with this id and all of its messages, or `None`."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[Conversation]:
        """Return `user_id`'s conversations, most-recently-updated first.

        Summaries only: each `Conversation.messages` is empty. Callers that need the
        turns of a specific thread call `get`.
        """
        raise NotImplementedError

    @abstractmethod
    async def ensure(self, conversation_id: str, user_id: str) -> None:
        """Create the conversation if it doesn't exist yet; do nothing if it does.

        Idempotent, because the chat stream can't know whether a `thread_id` is new: the
        frontend mints the id locally and only sends it with the first message. Two rapid
        turns on a brand-new thread would race a `get`-then-`create` pair, so this is one
        upsert rather than a check followed by an insert.
        """
        raise NotImplementedError

    @abstractmethod
    async def append_messages(self, conversation_id: str, messages: Sequence[Message]) -> None:
        """Append `messages` to the end of the conversation and bump its `updated_at`."""
        raise NotImplementedError

    @abstractmethod
    async def update_title(self, conversation_id: str, title: str) -> None:
        """Set the conversation's display title."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, conversation_id: str) -> None:
        """Delete the conversation and, by cascade, all of its messages."""
        raise NotImplementedError
