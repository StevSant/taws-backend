"""Regression tests for `StreamAndPersistReply` — chat turns must reach the database.

The bug these pin down: chat history was never persisted at all. The
`ConversationRepository` adapter was a stub holding an in-process dict, the only use case
that called `save()` was never routed, and `POST /chat/stream` went straight from the router
to the agent graph without touching a repository — so a conversation existed only in the
LangGraph checkpointer (a cache) and in the browser's localStorage.

What must stay true:
- a completed exchange writes BOTH the user message and the assembled assistant reply;
- the assistant reply is the concatenation of the streamed tokens, written once at the end
  rather than per token;
- a stream that errored still records the user's own message, but no assistant reply;
- a persistence failure NEVER breaks the stream, because by then the client has already
  received every frame of the answer.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest

from app.application.chat.use_cases import StreamAndPersistReply, StreamReply
from app.application.chat.use_cases.stream_and_persist_reply import _pending_persist_tasks
from app.domain.agents.entities import (
    AgentStreamEvent,
    ChartEvent,
    CitationsEvent,
    ErrorEvent,
    Message,
    MessageRole,
    TokenEvent,
)
from app.domain.agents.ports import AgentRunner
from app.domain.chat.entities import Conversation
from app.domain.chat.ports import ConversationRepository
from app.domain.market.entities import (
    AssetClass,
    Instrument,
    NewsBrowseQuery,
    NewsFacets,
    NewsItem,
    PaginatedNewsItems,
)
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository


class _FakeAgentRunner(AgentRunner):
    """Streams the given events verbatim."""

    def __init__(self, events: list[AgentStreamEvent]) -> None:
        self._events = events

    async def stream(
        self,
        thread_id: str,
        message: Message,
        user_id: str,
        locale: str = "es",
        grounding_context: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        for event in self._events:
            yield event


class _FakeConversationRepository(ConversationRepository):
    """Records what was ensured and appended; optionally blows up on write."""

    def __init__(self, fail_on_write: bool = False) -> None:
        self.ensured: list[tuple[str, str]] = []
        self.appended: list[tuple[str, list[Message]]] = []
        self._fail_on_write = fail_on_write

    async def get(self, conversation_id: str) -> Conversation | None:
        return None

    async def list_for_user(self, user_id: str) -> list[Conversation]:
        return []

    async def ensure(self, conversation_id: str, user_id: str) -> None:
        if self._fail_on_write:
            raise RuntimeError("supabase is down")
        self.ensured.append((conversation_id, user_id))

    async def append_messages(self, conversation_id: str, messages: Sequence[Message]) -> None:
        if self._fail_on_write:
            raise RuntimeError("supabase is down")
        self.appended.append((conversation_id, list(messages)))

    async def update_title(self, conversation_id: str, title: str) -> None:
        return None

    async def delete(self, conversation_id: str) -> None:
        return None


class _FakeInstrumentUniverse(InstrumentUniverse):
    def all(self) -> list[Instrument]:
        return []

    def by_symbol(self, symbol: str) -> Instrument | None:
        return None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return []


class _FakeNewsItemRepository(NewsItemRepository):
    async def upsert_many(self, items: list[NewsItem]) -> list[NewsItem]:
        return items

    async def get_by_id(self, news_id: str) -> NewsItem | None:
        return None

    async def browse(self, query: NewsBrowseQuery) -> PaginatedNewsItems:
        return PaginatedNewsItems(items=[], total=0, page=1, page_size=0)

    async def list_facets(self) -> NewsFacets:
        return NewsFacets(sources=[], providers=[])

    async def list_pending(self, limit: int) -> list[NewsItem]:
        return []

    async def list_unscored(self, limit: int) -> list[NewsItem]:
        return []

    async def save_sentiment_scores(self, scores_by_id: dict[str, float]) -> None:
        return None

    async def list_recent(
        self, symbols: list[str] | None, since_hours: int, limit: int
    ) -> list[NewsItem]:
        return []

    async def list_related(self, item: NewsItem, limit: int) -> list[NewsItem]:
        return []

    async def list_for_symbol_in_range(self, symbol, from_date, to_date, limit) -> list[NewsItem]:
        return []

    async def update_analysis_status(
        self, news_item_id, status, signal_id=None, skip_reason=None
    ) -> NewsItem:
        raise NotImplementedError


def _build(
    events: list[AgentStreamEvent], repository: ConversationRepository
) -> StreamAndPersistReply:
    return StreamAndPersistReply(
        stream_reply=StreamReply(
            agent_runner=_FakeAgentRunner(events),
            instrument_universe=_FakeInstrumentUniverse(),
            news_item_repository=_FakeNewsItemRepository(),
        ),
        conversation_repository=repository,
    )


async def _drain(stream: AsyncIterator[AgentStreamEvent]) -> list[AgentStreamEvent]:
    events = [event async for event in stream]
    # `execute` now schedules `_persist_turn` as a fire-and-forget background task after the
    # final frame (done-first streaming), so draining the stream no longer guarantees the write
    # has run. Await the module's pending-task set so the repository assertions below are
    # deterministic instead of racing the event loop.
    await asyncio.gather(*_pending_persist_tasks)
    return events


async def test_completed_exchange_persists_user_message_and_assembled_reply() -> None:
    repository = _FakeConversationRepository()
    use_case = _build(
        [TokenEvent(token="Hola"), TokenEvent(token=", "), TokenEvent(token="mundo")],
        repository,
    )

    events = await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            "es",
        )
    )

    # the stream itself is untouched — the decorator forwards every frame
    assert len(events) == 3

    assert repository.ensured == [("thread-1", "user-1")]
    conversation_id, messages = repository.appended[0]
    assert conversation_id == "thread-1"
    assert [(m.role, m.content) for m in messages] == [
        (MessageRole.USER, "hi"),
        (MessageRole.ASSISTANT, "Hola, mundo"),
    ]


async def test_charts_streamed_in_the_turn_are_persisted_on_the_reply() -> None:
    """A chart the assistant drew must survive a reload — it is stored on the assistant turn.

    The bug this pins: `ChartEvent`s were streamed to the client but never persisted, so a
    reopened thread rehydrated a text-only transcript and the charts silently vanished.
    """
    repository = _FakeConversationRepository()
    chart_a = {"type": "candlestick", "meta": {"title": "BTC"}}
    chart_b = {"type": "line", "meta": {"title": "BTC 1Y"}}
    use_case = _build(
        [
            TokenEvent(token="BTC "),
            ChartEvent(chart=chart_a),
            TokenEvent(token="cotiza"),
            ChartEvent(chart=chart_b),
        ],
        repository,
    )

    await _drain(
        use_case.execute("thread-1", Message(role=MessageRole.USER, content="btc?"), "user-1", "es")
    )

    _, messages = repository.appended[0]
    assert [m.charts for m in messages] == [[], [chart_a, chart_b]]
    assert messages[1].content == "BTC cotiza"


async def test_citations_streamed_in_the_turn_are_persisted_on_the_reply() -> None:
    repository = _FakeConversationRepository()
    citations = [
        {
            "kind": "news",
            "claim": "CPI supported BTC.",
            "publisher": "Reuters",
            "title": "Inflation cools",
            "url": "https://example.com/cpi",
            "published_at": "2026-07-15T12:00:00Z",
        }
    ]
    use_case = _build(
        [TokenEvent(token="BTC outlook"), CitationsEvent(citations=citations)],
        repository,
    )

    await _drain(
        use_case.execute("thread-1", Message(role=MessageRole.USER, content="btc?"), "user-1", "es")
    )

    _, messages = repository.appended[0]
    assert messages[1].citations == citations


async def test_only_one_write_per_turn_not_one_per_token() -> None:
    repository = _FakeConversationRepository()
    use_case = _build([TokenEvent(token=str(index)) for index in range(50)], repository)

    await _drain(
        use_case.execute("thread-1", Message(role=MessageRole.USER, content="hi"), "user-1", "es")
    )

    assert len(repository.appended) == 1


async def test_errored_stream_persists_the_user_message_but_no_reply() -> None:
    repository = _FakeConversationRepository()
    use_case = _build(
        [TokenEvent(token="partial"), ErrorEvent(message="model exploded")], repository
    )

    await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            "es",
        )
    )

    _, messages = repository.appended[0]
    assert [(m.role, m.content) for m in messages] == [(MessageRole.USER, "hi")]


async def test_persistence_failure_does_not_break_the_stream() -> None:
    """The reply is already on the wire by the time we write; a DB fault must not abort it."""
    repository = _FakeConversationRepository(fail_on_write=True)
    use_case = _build([TokenEvent(token="a"), TokenEvent(token="b")], repository)

    events = await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            "es",
        )
    )

    assert [event.token for event in events if isinstance(event, TokenEvent)] == ["a", "b"]
    assert repository.appended == []


@pytest.mark.parametrize("thread_id", ["default", "1752384000000-0.123456"])
async def test_persists_under_non_uuid_thread_ids(thread_id: str) -> None:
    """`conversations.id` is `text`, not `uuid`, precisely so these two ids work.

    The router substitutes the literal `"default"` when a request omits `thread_id`, and the
    frontend falls back to `${Date.now()}-${Math.random()}` where `crypto.randomUUID` is
    unavailable. A `uuid` column would reject both at insert time.
    """
    repository = _FakeConversationRepository()
    use_case = _build([TokenEvent(token="ok")], repository)

    await _drain(
        use_case.execute(thread_id, Message(role=MessageRole.USER, content="hi"), "user-1", "es")
    )

    assert repository.ensured == [(thread_id, "user-1")]
