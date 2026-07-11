from app.domain.agents.entities import Message, MessageRole
from app.domain.chat.entities import Conversation
from app.domain.chat.ports import ConversationRepository


class SendMessage:
    """Appends a user message to a conversation (creating it if needed) and persists it.

    Depends only on the `ConversationRepository` port — constructor injection keeps
    this use case unaware of whatever adapter (Supabase, in-memory, ...) backs it.
    """

    def __init__(self, conversation_repository: ConversationRepository) -> None:
        self._conversation_repository = conversation_repository

    async def execute(self, conversation_id: str, user_id: str, content: str) -> Conversation:
        conversation = await self._conversation_repository.get(conversation_id)
        if conversation is None:
            conversation = Conversation(id=conversation_id, user_id=user_id)

        conversation.messages.append(Message(role=MessageRole.USER, content=content))
        await self._conversation_repository.save(conversation)
        return conversation
