import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.v1.dependencies import (
    get_agent_runner,
    get_generate_conversation_title_use_case,
    get_realtime_session_provider,
    get_stt_provider,
    get_tts_provider,
    require_current_user,
)
from app.api.v1.schemas import (
    ChatRequest,
    ConversationTitleResponse,
    CurrentUser,
    GenerateTitleRequest,
    RealtimeSessionResponse,
    RealtimeToolRequest,
    RealtimeToolResponse,
    SpeakRequest,
    TranscriptionResponse,
)
from app.application.chat.use_cases import GenerateConversationTitle, StreamReply
from app.core.config import Settings, get_settings
from app.core.di import Container, get_container
from app.domain.agents.entities import (
    AgentStreamEvent,
    ChartEvent,
    ErrorEvent,
    Message,
    MessageRole,
    TokenEvent,
    ToolCallEvent,
    TraceEvent,
)
from app.domain.agents.ports import (
    AgentRunner,
    RealtimeSessionProvider,
    STTProvider,
    TTSProvider,
)
from app.infrastructure.realtime.tools import (
    ToolNotFoundError,
    build_realtime_tool_schemas,
    dispatch_realtime_tool,
    validate_tool_args,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_DEFAULT_THREAD_ID = "default"

_REALTIME_INSTRUCTIONS = (
    "You are TAWS Voice, a spoken market-intelligence assistant. Answer briefly and "
    "conversationally. Use the provided tools to ground every market claim in real "
    "data — call get_market_data for prices, get_news for headlines, list_signals for "
    "existing Analyst signals, and generate_signal to produce a fresh one (acknowledge "
    "verbally before that slower call). For broad news-impact questions, generate fresh "
    "signals for up to three related symbols returned by get_news. Omit unsupported impact "
    "or confidence fields instead of saying they are unspecified. Never give personalized "
    "financial advice; this is research and information only."
)


def _to_sse_frame(event: AgentStreamEvent) -> str:
    """Serialize one `AgentStreamEvent` to a single SSE v2 `data:` frame.

    Frame shapes (the wire contract the frontend's `SseChatRepository` parses):
    - `TokenEvent` -> `{"t": "<token>"}`
    - `TraceEvent` -> `{"trace": {"agent": "<name>", "event": "routing"|"start"|"done",
      "detail": "<optional text>"}}` (`detail` omitted when `None`)
    - `ErrorEvent` -> `{"error": "<message>"}`
    - `ChartEvent` -> `{"chart": {...}}` (a serialized ChartSpec wire dict)
    - `ToolCallEvent` -> `{"tool": {"agent": "<name>", "name": "<tool>", "event": "start"|"done"}}`
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
    elif isinstance(event, ChartEvent):
        payload = {"chart": event.chart}
    elif isinstance(event, ToolCallEvent):
        payload = {
            "tool": {
                "agent": event.tool.agent,
                "name": event.tool.name,
                "event": event.tool.event.value,
            }
        }
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
    user: Annotated[CurrentUser, Depends(require_current_user)],
    agent_runner: Annotated[AgentRunner, Depends(get_agent_runner)],
) -> StreamingResponse:
    """Stream an assistant reply over Server-Sent Events (SSE protocol v2).

    Delegates to the `AgentRunner` port (the Supervisor graph, under the
    `LangGraphAgentRunner` adapter — see `core/di/container.py`), which guards
    against a missing `OPENAI_API_KEY` with a placeholder streaming reply, so this
    endpoint never crashes before real keys are configured. Per-thread history is
    kept by the graph's checkpointer, keyed by `payload.thread_id`. Requires an
    authenticated user (see `require_current_user`); `user.id` is threaded through to
    the agent graph's config for future per-tenant tool access.
    """
    use_case = StreamReply(agent_runner=agent_runner)
    thread_id = payload.thread_id or _DEFAULT_THREAD_ID
    message = Message(role=MessageRole.USER, content=payload.message)

    event_stream = use_case.execute(thread_id, message, user.id)
    return StreamingResponse(_to_sse(event_stream), media_type="text/event-stream")


@router.post("/title", response_model=ConversationTitleResponse)
async def generate_title(
    payload: GenerateTitleRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    use_case: Annotated[
        GenerateConversationTitle, Depends(get_generate_conversation_title_use_case)
    ],
) -> ConversationTitleResponse:
    """Generate a concise 3-6 word topic title for a conversation.

    Called by the frontend after the first exchange (and again when the topic shifts) to
    replace the transient first-message title in the sessions sidebar. Reuses the Midas
    voice via the injected use case. Auth-gated like `/stream`; degrades gracefully to a
    short slice of the first user message when the LLM is unavailable (e.g. no API key),
    so it never fails the caller.
    """
    messages = [
        Message(role=item.role, content=item.content) for item in payload.messages
    ]
    title = await use_case.execute(messages)
    return ConversationTitleResponse(title=title)


@router.post("/realtime/session", response_model=RealtimeSessionResponse)
async def create_realtime_session(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    provider: Annotated[
        RealtimeSessionProvider | None, Depends(get_realtime_session_provider)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RealtimeSessionResponse:
    """Mint a short-lived OpenAI Realtime session for the browser's WebRTC connection.

    Requires an authenticated user. Returns 503 when the Realtime feature is disabled or
    unconfigured (`get_realtime_session_provider` -> `None`), so the frontend can hide the
    Talk button and fall back to text chat. The server authors the tool schema list and
    instructions here — the browser never chooses which tools the session exposes — and
    the acting `user_id` comes from the verified JWT. Only the ephemeral `ek_*` secret is
    returned; the real Realtime API key never leaves the backend.
    """
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime voice is not enabled",
        )

    tools = build_realtime_tool_schemas()
    session = await provider.mint_ephemeral_session(
        user_id=user.id,
        model=settings.openai_realtime_model,
        voice=settings.openai_realtime_voice,
        instructions=_REALTIME_INSTRUCTIONS,
        tools=tools,
        expires_in_seconds=settings.openai_realtime_ttl_seconds,
    )
    return RealtimeSessionResponse(
        client_secret=session.client_secret,
        model=session.model,
        expires_at=session.expires_at,
        tools=session.tools,
    )


@router.post("/realtime/tool", response_model=RealtimeToolResponse)
async def execute_realtime_tool(
    payload: RealtimeToolRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    container: Annotated[Container, Depends(get_container)],
) -> RealtimeToolResponse:
    """Execute one model-relayed function call server-side and return its output.

    Security boundary (the browser relays whatever the model emits):
    - `payload.name` must be in the server allowlist — otherwise 400 (never dispatched).
    - `payload.arguments` are validated against the tool's Pydantic schema — 422 on bad
      input, before any handler runs.
    - the acting `user_id` is taken from the verified JWT (`user.id`), NEVER from
      `payload.arguments`.

    Once past validation, a tool/use-case failure is caught and returned as a structured
    `{"error": ...}` output (HTTP 200) so the voice model can recover verbally, rather
    than surfacing a 500 mid-conversation.
    """
    try:
        validate_tool_args(payload.name, payload.arguments)
    except ToolNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        ) from exc

    try:
        output = await dispatch_realtime_tool(
            container, payload.name, payload.arguments, user.id
        )
    except Exception as exc:  # noqa: BLE001 — recoverable tool error, not a server fault
        logger.warning(
            "Realtime tool %r failed for call %r", payload.name, payload.call_id,
            exc_info=True,
        )
        output = {"error": str(exc)}

    return RealtimeToolResponse(call_id=payload.call_id, output=output)


@router.post("/speak")
async def speak(
    payload: SpeakRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    tts_provider: Annotated[TTSProvider | None, Depends(get_tts_provider)],
) -> Response:
    """Synthesize `payload.text` into spoken audio and return it as a single buffer.

    Auth-gated via `require_current_user`, same as `/stream`. When TTS isn't configured
    the DI-resolved `tts_provider` is `None` (see `Container.get_tts_provider`) — this
    endpoint returns 503 in that case, the signal for the frontend to fall back to the
    browser's built-in speech synthesis. The voice defaults to the server-configured
    `tts_voice` when the request omits one; the audio format is always the configured
    `tts_response_format` (mp3 -> `audio/mpeg`). Buffered, not streamed — see the
    `TTSProvider` port's docstring for why (OpenAI TTS has no stream-to-service).
    """
    if len(payload.text) > settings.tts_max_input_chars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Text exceeds the maximum of {settings.tts_max_input_chars} "
                "characters for speech synthesis."
            ),
        )
    if tts_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech is not configured on this server.",
        )
    audio = await tts_provider.synthesize(
        payload.text,
        payload.voice or settings.tts_voice,
        settings.tts_response_format,
    )
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[CurrentUser, Depends(require_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    stt_provider: Annotated[STTProvider | None, Depends(get_stt_provider)],
) -> TranscriptionResponse:
    """Transcribe an uploaded audio clip into text (the mirror image of `/speak`).

    Lets a user dictate a chat message by voice. Auth-gated via `require_current_user`,
    same as `/stream` and `/speak`. When STT isn't configured the DI-resolved
    `stt_provider` is `None` (see `Container.get_stt_provider`) — this endpoint returns
    503 in that case, the signal for the frontend to fall back to the browser's built-in
    speech recognition. Audio over the configured `stt_max_audio_bytes` cap (or empty) is
    rejected with 422 BEFORE the billed transcription API is hit, capping per-request
    cost / DoS blast radius.
    """
    audio = await file.read()

    if stt_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech-to-text is not configured on this server.",
        )
    if len(audio) > settings.stt_max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Audio exceeds the maximum of {settings.stt_max_audio_bytes} "
                "bytes for transcription."
            ),
        )
    if not audio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Audio file is empty.",
        )

    text = await stt_provider.transcribe(
        audio,
        file.filename or "audio",
        file.content_type or "application/octet-stream",
    )
    return TranscriptionResponse(text=text)
