"""Endpoint test for `POST /api/v1/chat/stream` optional reference grounding (issue #73).

Drives the real route via `TestClient` with DI overrides, asserting that an
`asset_symbol` (or `news_id`) in the request body is resolved through the
`InstrumentUniverse` / `NewsItemRepository` ports and forwarded to the `AgentRunner`
as `grounding_context`. With no reference the runner is streamed `grounding_context=None`,
exactly as today.
"""

from collections.abc import AsyncIterator, Sequence

from fastapi.testclient import TestClient

from app.api.v1.dependencies import (
    get_agent_runner,
    get_conversation_repository,
    get_instrument_universe,
    get_news_item_repository,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser
from app.domain.agents.entities import AgentStreamEvent, Message, TokenEvent
from app.domain.agents.ports import AgentRunner
from app.domain.chat.entities import Conversation
from app.domain.chat.ports import ConversationRepository
from app.domain.market.entities import (
    AssetClass,
    Instrument,
    NewsBrowseQuery,
    NewsFacets,
    PaginatedNewsItems,
)
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository
from app.main import app

_USER_ID = "dev-user"


class _RecordingAgentRunner(AgentRunner):
    """Records the `grounding_context` it was streamed with; yields one token."""

    def __init__(self) -> None:
        self.grounding_context: str | None = None
        self.called = False

    async def stream(
        self,
        thread_id: str,
        message: Message,
        user_id: str,
        locale: str = "es",
        grounding_context: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.called = True
        self.grounding_context = grounding_context
        yield TokenEvent(token="ok")


class _FakeInstrumentUniverse(InstrumentUniverse):
    def all(self) -> list[Instrument]:
        return [self._instrument()]

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._instrument() if symbol.upper() == "AAPL" else None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return []

    @staticmethod
    def _instrument() -> Instrument:
        return Instrument(
            symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"
        )


class _EmptyNewsItemRepository(NewsItemRepository):
    async def upsert_many(self, items):
        return items

    async def get_by_id(self, news_id: str):
        return None

    async def browse(self, query: NewsBrowseQuery) -> PaginatedNewsItems:
        return PaginatedNewsItems(items=[], total=0, page=1, page_size=0)

    async def list_facets(self) -> NewsFacets:
        return NewsFacets(sources=[], providers=[])

    async def list_pending(self, limit: int):
        return []

    async def list_unscored(self, limit: int):
        return []

    async def save_sentiment_scores(self, scores_by_id: dict[str, float]) -> None:
        return None

    async def list_recent(self, symbols, since_hours: int, limit: int):
        return []

    async def list_related(self, item, limit: int):
        return []

    async def list_for_symbol_in_range(self, symbol, from_date, to_date, limit):
        return []

    async def update_analysis_status(self, news_item_id, status, signal_id=None, skip_reason=None):
        raise NotImplementedError


class _NullConversationRepository(ConversationRepository):
    """Swallows the persistence `StreamAndPersistReply` now performs after the stream.

    These tests assert what reaches the `AgentRunner`, not what reaches the database — but
    the route persists the finished turn, so without this override the container would build
    a real Supabase-backed repository and the test would try to talk to the network.
    """

    async def get(self, conversation_id: str) -> Conversation | None:
        return None

    async def list_for_user(self, user_id: str) -> list[Conversation]:
        return []

    async def ensure(self, conversation_id: str, user_id: str) -> None:
        return None

    async def append_messages(self, conversation_id: str, messages: Sequence[Message]) -> None:
        return None

    async def update_title(self, conversation_id: str, title: str) -> None:
        return None

    async def delete(self, conversation_id: str) -> None:
        return None


def _override_common(runner: AgentRunner) -> None:
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="dev@example.com"
    )
    app.dependency_overrides[get_agent_runner] = lambda: runner
    app.dependency_overrides[get_instrument_universe] = _FakeInstrumentUniverse
    app.dependency_overrides[get_news_item_repository] = _EmptyNewsItemRepository
    app.dependency_overrides[get_conversation_repository] = _NullConversationRepository


def test_asset_symbol_is_forwarded_as_grounding_context() -> None:
    runner = _RecordingAgentRunner()
    _override_common(runner)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/stream",
                json={"message": "hi", "asset_symbol": "AAPL"},
            )
            # Drain the SSE stream so the generator runs to completion.
            _ = response.text
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert runner.called
    assert runner.grounding_context is not None
    assert "AAPL" in runner.grounding_context


def test_no_reference_forwards_none_grounding_context() -> None:
    runner = _RecordingAgentRunner()
    _override_common(runner)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/stream", json={"message": "hi"})
            _ = response.text
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert runner.called
    assert runner.grounding_context is None
