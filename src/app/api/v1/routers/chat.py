import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.v1.dependencies import get_agent_runner
from app.api.v1.schemas import ChatRequest
from app.application.chat.use_cases import StreamReply
from app.domain.agents.entities import (
    AgentStreamEvent,
    ErrorEvent,
    Message,
    MessageRole,
    TokenEvent,
    TraceEvent,
)
from app.domain.agents.ports import AgentRunner

router = APIRouter(prefix="/chat", tags=["chat"])

_DEFAULT_THREAD_ID = "default"


def _to_sse_frame(event: AgentStreamEvent) -> str:
    """Serialize one `AgentStreamEvent` to a single SSE v2 `data:` frame.

    Frame shapes (the wire contract the frontend's `SseChatRepository` parses):
    - `TokenEvent` -> `{"t": "<token>"}`
    - `TraceEvent` -> `{"trace": {"agent": "<name>", "event": "routing"|"start"|"done",
      "detail": "<optional text>"}}` (`detail` omitted when `None`)
    - `ErrorEvent` -> `{"error": "<message>"}`
    """
    payload: dict[str, Any]
    if isinstance(event, TokenEvent):
        payload = {"t": event.token}
    elif isinstance(event, TraceEvent):
        trace_payload: dict[str, Any] = {
            "agent": event.trace.agent,
            "event": event.trace.event.value,
        }
        if event.trace.detail is not None:
            trace_payload["detail"] = event.trace.detail
        payload = {"trace": trace_payload}
    elif isinstance(event, ErrorEvent):
        payload = {"error": event.message}
    else:
        raise TypeError(f"Unhandled AgentStreamEvent variant: {event!r}")
    return f"data: {json.dumps(payload)}\n\n"


async def _to_sse(events: AsyncIterator[AgentStreamEvent]) -> AsyncIterator[str]:
    """Wrap an `AgentStreamEvent` stream as `text/event-stream` frames.

    Each frame is a JSON object rather than a raw token, so tokens containing
    newlines or other SSE-significant characters can't corrupt the frame; the
    stream always ends with `data: {"done": true}\\n\\n`, even after an `ErrorEvent`
    frame, so clients can rely on `done` to know the stream is over either way.
    """
    async for event in events:
        yield _to_sse_frame(event)
    yield f"data: {json.dumps({'done': True})}\n\n"


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    agent_runner: Annotated[AgentRunner, Depends(get_agent_runner)],
) -> StreamingResponse:
    """Stream an assistant reply over Server-Sent Events (SSE protocol v2).

    Delegates to the `AgentRunner` port (the Supervisor graph, under the
    `LangGraphAgentRunner` adapter — see `core/di/container.py`), which guards
    against a missing `OPENAI_API_KEY` with a placeholder streaming reply, so this
    endpoint never crashes before real keys are configured. Per-thread history is
    kept by the graph's checkpointer, keyed by `payload.thread_id`.
    """
    use_case = StreamReply(agent_runner=agent_runner)
    thread_id = payload.thread_id or _DEFAULT_THREAD_ID
    message = Message(role=MessageRole.USER, content=payload.message)

    event_stream = use_case.execute(thread_id, message)
    return StreamingResponse(_to_sse(event_stream), media_type="text/event-stream")
