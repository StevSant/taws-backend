import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.v1.dependencies import get_agent_runner
from app.api.v1.schemas import ChatRequest
from app.application.chat.use_cases import StreamReply
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import AgentRunner

router = APIRouter(prefix="/chat", tags=["chat"])

_DEFAULT_THREAD_ID = "default"


async def _to_sse(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Wrap a token stream as `text/event-stream` frames.

    Each frame is a JSON object (`data: {"t": "<token>"}\\n\\n`) rather than a raw
    token, so tokens containing newlines or other SSE-significant characters can't
    corrupt the frame; the stream ends with `data: {"done": true}\\n\\n`.
    """
    async for token in tokens:
        yield f"data: {json.dumps({'t': token})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    agent_runner: Annotated[AgentRunner, Depends(get_agent_runner)],
) -> StreamingResponse:
    """Stream an assistant reply over Server-Sent Events, token by token.

    Delegates to the `AgentRunner` port (a compiled LangGraph graph under the
    `LangGraphAgentRunner` adapter — see `core/di/container.py`), which guards
    against a missing `OPENAI_API_KEY` with a placeholder streaming reply, so this
    endpoint never crashes before real keys are configured. Per-thread history is
    kept by the graph's checkpointer, keyed by `payload.thread_id`.
    """
    use_case = StreamReply(agent_runner=agent_runner)
    thread_id = payload.thread_id or _DEFAULT_THREAD_ID
    message = Message(role=MessageRole.USER, content=payload.message)

    token_stream = use_case.execute(thread_id, message)
    return StreamingResponse(_to_sse(token_stream), media_type="text/event-stream")
