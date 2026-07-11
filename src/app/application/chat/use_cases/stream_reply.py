from collections.abc import AsyncIterator

from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.chat.ports import ConversationRepository


class StreamReply:
    """Streams an assistant reply token-by-token, then persists the full reply.

    Depends only on `LLMProvider` and `ConversationRepository` ports.
    """

    def __init__(
        self, llm_provider: LLMProvider, conversation_repository: ConversationRepository
    ) -> None:
        self._llm_provider = llm_provider
        self._conversation_repository = conversation_repository

    async def execute(self, conversation_id: str, messages: list[Message]) -> AsyncIterator[str]:
        reply_chunks: list[str] = []
        async for token in self._llm_provider.stream(messages):
            reply_chunks.append(token)
            yield token

        conversation = await self._conversation_repository.get(conversation_id)
        if conversation is not None:
            conversation.messages.append(
                Message(role=MessageRole.ASSISTANT, content="".join(reply_chunks))
            )
            await self._conversation_repository.save(conversation)
