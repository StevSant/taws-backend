import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from app.application.chat.use_cases.stream_reply import StreamReply
from app.domain.agents.entities import (
    AgentStreamEvent,
    ChartEvent,
    CitationsEvent,
    ErrorEvent,
    Message,
    MessageRole,
    TokenEvent,
)
from app.domain.chat.ports import ConversationRepository

logger = logging.getLogger(__name__)

# Strong references to in-flight background persistence tasks. `asyncio.create_task` only holds a
# weak reference to its task, so a scheduled write can be garbage-collected mid-flight before it
# finishes; keeping it here until it completes prevents that. Each task removes itself via a
# done callback (see `execute`), so the set holds only genuinely pending writes.
_pending_persist_tasks: set[asyncio.Task[None]] = set()


class StreamAndPersistReply:
    """Streams an assistant reply and writes the completed turn to the conversation store.

    `StreamReply` stays exactly what it was — a pure pass-through to the agent layer that
    persists nothing. This use case decorates it: it forwards every `AgentStreamEvent`
    onward untouched while accumulating the assistant's tokens, then saves the user message
    and the assembled reply once the stream is done.

    **Why persistence happens after the stream, and is scheduled rather than awaited.** The
    reply only exists as a sequence of `TokenEvent`s; there is no complete assistant message
    to store until the last one has been yielded, so the write cannot *begin* until the stream
    is done. Writing per-token would mean one database round-trip per token — the same mistake
    the frontend made writing `localStorage` on every token. But the write must not *delay* the
    stream either: `execute` schedules `_persist_turn` as a background task
    (`asyncio.create_task`) after the final frame instead of awaiting it inline, so the router's
    terminal `{"done": true}` frame reaches the client immediately rather than sitting behind
    four sequential Supabase round-trips (ensure + ordinal SELECT + insert + touch). The
    accepted tradeoff is a small lost-write window: if the process dies in the instant between
    the last frame and the background write completing, that turn is lost — but previously the
    client simply waited through that same write before it ever saw `done`. Because the task is
    fire-and-forget, its failure can never surface to the caller, so `_persist_turn` keeps its
    own try/except (below) and must never raise into an unobserved task exception.

    **Why a persistence failure never fails the stream.** By the time we write, the client
    has already received every frame of a successful reply. Raising here would abort the
    generator *after* the user has read the answer, turning a delivered reply into a broken
    connection and losing nothing but gaining a visible error. So a write failure is logged
    at WARNING and swallowed — the same reasoning `ResolveLocale` documents for swallowing
    its own profile-lookup errors around a `StreamingResponse`.

    **Why a failed turn still persists the user's message.** If the agent errored, the reply
    is not stored (there is no reply), but the user's message is: they did say it, the
    frontend shows it in the transcript, and dropping it server-side would make a reload
    silently rewrite the user's own history.
    """

    def __init__(
        self,
        stream_reply: StreamReply,
        conversation_repository: ConversationRepository,
        persist_retry_max_attempts: int = 1,
        persist_retry_backoff_seconds: float = 0.0,
    ) -> None:
        self._stream_reply = stream_reply
        self._conversation_repository = conversation_repository
        # Default of 1 attempt = the historical no-retry behavior; the chat router passes
        # the configured `Settings.chat_persist_retry_*` values (see `.env.example`).
        self._persist_retry_max_attempts = max(1, persist_retry_max_attempts)
        self._persist_retry_backoff_seconds = persist_retry_backoff_seconds

    async def execute(
        self,
        thread_id: str,
        message: Message,
        user_id: str,
        locale: str,
        asset_symbol: str | None = None,
        news_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        reply_tokens: list[str] = []
        reply_charts: list[dict[str, Any]] = []
        reply_citations: list[dict[str, Any]] = []
        errored = False

        async for event in self._stream_reply.execute(
            thread_id,
            message,
            user_id,
            locale,
            asset_symbol=asset_symbol,
            news_id=news_id,
            from_date=from_date,
            to_date=to_date,
        ):
            if isinstance(event, TokenEvent):
                reply_tokens.append(event.token)
            elif isinstance(event, ChartEvent):
                reply_charts.append(event.chart)
            elif isinstance(event, CitationsEvent):
                reply_citations = event.citations
            elif isinstance(event, ErrorEvent):
                errored = True
            yield event

        task = asyncio.create_task(
            self._persist_turn(
                thread_id=thread_id,
                user_id=user_id,
                message=message,
                reply="".join(reply_tokens),
                charts=reply_charts,
                citations=reply_citations,
                errored=errored,
            )
        )
        _pending_persist_tasks.add(task)
        task.add_done_callback(_pending_persist_tasks.discard)
        logger.debug(
            "Scheduled background persistence for chat turn on thread %r (user %r) after the "
            "terminal stream frame",
            thread_id,
            user_id,
        )

    async def _persist_turn(
        self,
        thread_id: str,
        user_id: str,
        message: Message,
        reply: str,
        charts: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        errored: bool,
    ) -> None:
        turn = [message]
        if reply and not errored:
            turn.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=reply,
                    charts=charts,
                    citations=citations,
                )
            )

        # Bounded retry with linear backoff (attempt * base). A turn that fails to persist
        # leaves a "ghost" conversation the frontend can never rehydrate — and the main way
        # this write fails in practice is the brief window around an App Runner deploy, which
        # a couple of spaced retries outlive. Accepted edge: `append_messages` is not atomic
        # (insert + touch), so a retry after a failure BETWEEN those two steps can duplicate
        # the turn — rarer and more benign than silently losing it.
        for attempt in range(1, self._persist_retry_max_attempts + 1):
            try:
                await self._conversation_repository.ensure(thread_id, user_id)
                await self._conversation_repository.append_messages(thread_id, turn)
                return
            except Exception:  # noqa: BLE001 — reply already delivered; see class docstring
                if attempt == self._persist_retry_max_attempts:
                    logger.warning(
                        "Failed to persist chat turn for thread %r (user %r) after %d "
                        "attempt(s); the reply was streamed to the client but will not "
                        "survive a reload",
                        thread_id,
                        user_id,
                        attempt,
                        exc_info=True,
                    )
                    return
                logger.warning(
                    "Persisting chat turn for thread %r (user %r) failed on attempt %d/%d; "
                    "retrying",
                    thread_id,
                    user_id,
                    attempt,
                    self._persist_retry_max_attempts,
                    exc_info=True,
                )
                await asyncio.sleep(self._persist_retry_backoff_seconds * attempt)
