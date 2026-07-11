from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.v1.dependencies import get_conversation_repository, get_llm_provider
from app.api.v1.schemas import ChatRequest
from app.application.chat.use_cases import StreamReply
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.chat.ports import ConversationRepository

router = APIRouter(prefix="/chat", tags=["chat"])

_DEFAULT_THREAD_ID = "default"


async def _to_sse(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Wrap a token stream as `text/event-stream` frames."""
    async for token in tokens:
        yield f"data: {token}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> StreamingResponse:
    """Stream an assistant reply over Server-Sent Events, token by token.

    Skeleton behavior: echoes the configured LLMProvider's stream (which itself
    guards against a missing OPENAI_API_KEY with a placeholder reply), so this
    endpoint never crashes before real keys/agents are wired up.
    """
    use_case = StreamReply(
        llm_provider=llm_provider, conversation_repository=conversation_repository
    )
    thread_id = payload.thread_id or _DEFAULT_THREAD_ID
    messages = [Message(role=MessageRole.USER, content=payload.message)]

    token_stream = use_case.execute(thread_id, messages)
    return StreamingResponse(_to_sse(token_stream), media_type="text/event-stream")
