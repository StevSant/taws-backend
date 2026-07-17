import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.v1.dependencies import (
    get_agent_runner,
    get_conversation_repository,
    get_generate_conversation_title_use_case,
    get_instrument_universe,
    get_news_item_repository,
    get_realtime_session_provider,
    get_resolve_locale_use_case,
    get_stt_provider,
    get_tts_provider,
    require_current_user,
)
from app.api.v1.schemas import (
    ChatRequest,
    ConversationDetailResponse,
    ConversationSummaryResponse,
    ConversationTitleResponse,
    CurrentUser,
    GenerateTitleRequest,
    RealtimeSessionResponse,
    RealtimeToolRequest,
    RealtimeToolResponse,
    RealtimeTurnsRequest,
    SpeakRequest,
    TranscriptionResponse,
)
from app.application.chat.use_cases import (
    GenerateConversationTitle,
    StreamAndPersistReply,
    StreamReply,
)
from app.application.profile.use_cases import ResolveLocale
from app.core.config import Settings, get_settings
from app.core.di import Container, get_container
from app.domain.agents.entities import (
    AgentStreamEvent,
    ChartEvent,
    CitationsEvent,
    ContributionsEvent,
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
from app.domain.chat.entities import Conversation
from app.domain.chat.ports import ConversationRepository
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository
from app.infrastructure.realtime import build_realtime_instructions, transcription_language
from app.infrastructure.realtime.tools import (
    ToolNotFoundError,
    build_realtime_tool_schemas,
    dispatch_realtime_tool,
    validate_tool_args,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_DEFAULT_THREAD_ID = "default"


def _to_sse_frame(event: AgentStreamEvent) -> str:
    """Serialize one `AgentStreamEvent` to a single SSE v2 `data:` frame.

    Frame shapes (the wire contract the frontend's `SseChatRepository` parses):
    - `TokenEvent` -> `{"t": "<token>"}`
    - `TraceEvent` -> `{"trace": {"agent": "<name>", "event": "routing"|"start"|"done",
      "detail": "<optional text>"}}` (`detail` omitted when `None`)
    - `ErrorEvent` -> `{"error": "<message>"}`
    - `ChartEvent` -> `{"chart": {...}}` (a serialized ChartSpec wire dict)
    - `CitationsEvent` -> `{"citations": [...]}`
    - `ContributionsEvent` -> `{"contributions": [{"agent", "stance", "confidence", "headline"}]}`
      (multi-specialist turns only)
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
    elif isinstance(event, CitationsEvent):
        payload = {"citations": event.citations}
    elif isinstance(event, ContributionsEvent):
        payload = {"contributions": event.contributions}
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


async def _get_owned_conversation(
    conversation_id: str,
    user: CurrentUser,
    repository: ConversationRepository,
) -> Conversation:
    """Return the conversation if it exists and belongs to `user`, else raise 404.

    The backend reaches Supabase with the service-role key, which bypasses the `auth.uid()`
    RLS policies on `conversations` — so ownership has to be enforced here, in the app, not
    left to the database. 404 (not 403) even when the row exists but belongs to someone
    else, so this endpoint never confirms another user's conversation id exists — same
    ownership-check shape as `notes.py`'s `_get_owned_note`.
    """
    conversation = await repository.get(conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


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
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    resolve_locale: Annotated[ResolveLocale, Depends(get_resolve_locale_use_case)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Stream an assistant reply over Server-Sent Events (SSE protocol v2), and persist it.

    Delegates to the `AgentRunner` port (the Supervisor graph, under the
    `LangGraphAgentRunner` adapter — see `core/di/container.py`), which guards
    against a missing `OPENAI_API_KEY` with a placeholder streaming reply, so this
    endpoint never crashes before real keys are configured. Requires an authenticated user
    (see `require_current_user`); `user.id` is threaded through to the agent graph's config
    for per-tenant tool access.

    **Two different things remember this conversation, and they are not interchangeable.**
    The graph's checkpointer (Redis, or `InMemoryCheckpointer` in development) holds the
    agent's working memory for the thread — that is what makes the next turn aware of the
    last one, and it is a cache. `StreamAndPersistReply` additionally writes the finished
    turn to the `conversations` table, which is what makes the thread survive a restart, a
    reload, or a move to another device. Chat previously had only the first of those, which
    is why history vanished: nothing was ever written to the database.

    An optional `payload.asset_symbol` or `payload.news_id` (issue #73) is resolved via
    the injected `InstrumentUniverse` / `NewsItemRepository` ports into a grounding string
    that anchors the agent's answer on that asset/news; omit both to behave as before.

    The reply's language is resolved BEFORE the stream opens (issue #67) — `payload.locale`,
    else the user's stored `preferred_locale`, else `Settings.default_locale` — because once
    `StreamingResponse` starts emitting frames there is no longer a way to fail a profile
    lookup cleanly. `ResolveLocale` swallows its own errors for the same reason.
    """
    use_case = StreamAndPersistReply(
        stream_reply=StreamReply(
            agent_runner=agent_runner,
            instrument_universe=instrument_universe,
            news_item_repository=news_item_repository,
        ),
        conversation_repository=conversation_repository,
        persist_retry_max_attempts=settings.chat_persist_retry_max_attempts,
        persist_retry_backoff_seconds=settings.chat_persist_retry_backoff_seconds,
    )
    thread_id = payload.thread_id or _DEFAULT_THREAD_ID
    message = Message(role=MessageRole.USER, content=payload.message)
    locale = await resolve_locale.execute(user_id=user.id, requested_locale=payload.locale)

    event_stream = use_case.execute(
        thread_id,
        message,
        user.id,
        locale,
        asset_symbol=payload.asset_symbol,
        news_id=payload.news_id,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    return StreamingResponse(_to_sse(event_stream), media_type="text/event-stream")


@router.post("/title", response_model=ConversationTitleResponse)
async def generate_title(
    payload: GenerateTitleRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    use_case: Annotated[
        GenerateConversationTitle, Depends(get_generate_conversation_title_use_case)
    ],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> ConversationTitleResponse:
    """Generate a concise 3-6 word topic title for a conversation, and save it.

    Called by the frontend after the first exchange (and again when the topic shifts) to
    replace the transient first-message title in the sessions sidebar. Reuses the Midas
    voice via the injected use case. Auth-gated like `/stream`; degrades gracefully to a
    short slice of the first user message when the LLM is unavailable (e.g. no API key),
    so it never fails the caller.

    When `payload.thread_id` names a conversation the caller owns, the title is persisted
    onto it, so the sidebar shows the same title after a reload and on other devices rather
    than each client re-deriving one locally. A title for a thread that doesn't exist (or
    isn't the caller's) is still returned but not saved — this endpoint computes a title,
    and refusing to do so because there's nothing to save it to would be a worse trade.
    """
    messages = [Message(role=item.role, content=item.content) for item in payload.messages]
    title = await use_case.execute(messages)

    if payload.thread_id is not None:
        conversation = await conversation_repository.get(payload.thread_id)
        if conversation is not None and conversation.user_id == user.id:
            await conversation_repository.update_title(payload.thread_id, title)

    return ConversationTitleResponse(title=title)


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
async def list_conversations(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> list[ConversationSummaryResponse]:
    """List the authenticated user's conversations, most-recently-updated first.

    This is what the sessions sidebar hydrates from. Summaries only — no message bodies;
    the turns of a thread come from `GET /chat/conversations/{conversation_id}`.
    """
    conversations = await conversation_repository.list_for_user(user.id)
    return [ConversationSummaryResponse.model_validate(item) for item in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> ConversationDetailResponse:
    """Return one conversation the caller owns, with all of its turns in order."""
    conversation = await _get_owned_conversation(conversation_id, user, conversation_repository)
    return ConversationDetailResponse.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> None:
    """Delete one conversation the caller owns, and its messages by cascade.

    Deleting a thread in the sidebar used to be a local-only operation, which orphaned
    whatever server-side state existed for that `thread_id`; it now removes the row too.
    """
    await _get_owned_conversation(conversation_id, user, conversation_repository)
    await conversation_repository.delete(conversation_id)


@router.post("/realtime/session", response_model=RealtimeSessionResponse)
async def create_realtime_session(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    provider: Annotated[RealtimeSessionProvider | None, Depends(get_realtime_session_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    resolve_locale: Annotated[ResolveLocale, Depends(get_resolve_locale_use_case)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
    locale: Annotated[str | None, Query(min_length=2, max_length=35)] = None,
) -> RealtimeSessionResponse:
    """Mint a short-lived OpenAI Realtime session for the browser's WebRTC connection.

    Requires an authenticated user. Returns 503 when the Realtime feature is disabled or
    unconfigured (`get_realtime_session_provider` -> `None`), so the frontend can hide the
    Talk button and fall back to text chat. The server authors the tool schema list and
    instructions here — the browser never chooses which tools the session exposes — and
    the acting `user_id` comes from the verified JWT. Only the ephemeral `ek_*` secret is
    returned; the real Realtime API key never leaves the backend.

    A real `conversations` row is created and its id returned as `conversation_id` (issue #6),
    so the browser can persist completed voice turns to it via `POST /chat/realtime/turns` —
    voice threads used to live only in frontend Signals and vanished on refresh. The
    conversation is bound BEFORE the (billed) mint so a mint failure never orphans a row.

    `locale` follows the same precedence as `/stream` (explicit request -> the user's stored
    `preferred_locale` -> `Settings.default_locale`) via the shared `ResolveLocale`. Until now
    this endpoint threaded no locale at all and minted every session with the bare English
    `REALTIME_INSTRUCTIONS`, which is why the voice agent answered Spanish users in English.
    """
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime voice is not enabled",
        )

    conversation_id = str(uuid4())
    await conversation_repository.ensure(conversation_id, user.id)

    effective_locale = await resolve_locale.execute(user_id=user.id, requested_locale=locale)
    tools = build_realtime_tool_schemas(charts_enabled=settings.charts_enabled)
    session = await provider.mint_ephemeral_session(
        user_id=user.id,
        model=settings.openai_realtime_model,
        voice=settings.openai_realtime_voice,
        instructions=build_realtime_instructions(effective_locale),
        tools=tools,
        expires_in_seconds=settings.openai_realtime_ttl_seconds,
        transcription_language=transcription_language(effective_locale),
    )
    session = replace(session, conversation_id=conversation_id)
    return RealtimeSessionResponse(
        client_secret=session.client_secret,
        model=session.model,
        expires_at=session.expires_at,
        tools=session.tools,
        conversation_id=session.conversation_id,
    )


@router.post("/realtime/turns", status_code=status.HTTP_204_NO_CONTENT)
async def append_realtime_turns(
    payload: RealtimeTurnsRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> None:
    """Append completed voice turns to their bound conversation (issue #6).

    The realtime data path runs browser<->OpenAI directly, so the backend never sees the
    turns as they happen; the browser calls this after each completed user+assistant exchange
    (or in a batch on stop) to persist them. Turns are written through the SAME
    `ConversationRepository.append_messages` the text chat's `StreamAndPersistReply` uses, so
    a refresh rehydrates a voice thread exactly like a text one via
    `GET /chat/conversations/{id}`.

    Requires the authenticated user and verifies they own `conversation_id` (404 otherwise,
    same ownership shape as every other conversation endpoint) so a caller can never write
    into another user's thread.
    """
    await _get_owned_conversation(payload.conversation_id, user, conversation_repository)
    messages = [Message(role=turn.role, content=turn.content) for turn in payload.turns]
    if messages:
        await conversation_repository.append_messages(payload.conversation_id, messages)


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        ) from exc

    try:
        output = await dispatch_realtime_tool(container, payload.name, payload.arguments, user.id)
    except Exception as exc:  # noqa: BLE001 — recoverable tool error, not a server fault
        logger.warning(
            "Realtime tool %r failed for call %r",
            payload.name,
            payload.call_id,
            exc_info=True,
        )
        output = {"error": str(exc)}

    logger.info(
        "Realtime tool %r completed for call %r (chart=%s)",
        payload.name,
        payload.call_id,
        "chart" in output,
    )
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
