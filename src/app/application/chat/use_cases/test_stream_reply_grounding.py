"""Unit tests for `StreamReply`'s optional reference grounding (issue #73).

`StreamReply.execute` gains two optional flat references — `asset_symbol` and
`news_id` — resolves at most one to a formatted `grounding_context` string via the
`InstrumentUniverse` / `NewsItemRepository` ports, and forwards it to
`AgentRunner.stream`. When neither is set (or the reference resolves to nothing)
`grounding_context` is `None` and behavior is exactly as before.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.application.chat.use_cases import StreamReply
from app.domain.agents.entities import AgentStreamEvent, Message, MessageRole, TokenEvent
from app.domain.agents.ports import AgentRunner
from app.domain.market.entities import AssetClass, Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository


class _FakeAgentRunner(AgentRunner):
    """Records the `grounding_context` it was streamed with; yields one token."""

    def __init__(self) -> None:
        self.grounding_context: str | None = None
        self.called = False

    async def stream(
        self,
        thread_id: str,
        message: Message,
        user_id: str,
        grounding_context: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.called = True
        self.grounding_context = grounding_context
        yield TokenEvent(token="ok")


class _FakeInstrumentUniverse(InstrumentUniverse):
    """Returns a single instrument by symbol; `None` otherwise."""

    def __init__(self, instrument: Instrument | None) -> None:
        self._instrument = instrument

    def all(self) -> list[Instrument]:
        return [self._instrument] if self._instrument else []

    def by_symbol(self, symbol: str) -> Instrument | None:
        if self._instrument and self._instrument.symbol.upper() == symbol.upper():
            return self._instrument
        return None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return []


class _FakeNewsItemRepository(NewsItemRepository):
    """Returns a single news item by id; `None` otherwise."""

    def __init__(self, item: NewsItem | None) -> None:
        self._item = item

    async def upsert_many(self, items: list[NewsItem]) -> list[NewsItem]:
        return items

    async def get_by_id(self, news_id: str) -> NewsItem | None:
        if self._item and self._item.id == news_id:
            return self._item
        return None

    async def list_pending(self, limit: int) -> list[NewsItem]:
        return []

    async def update_analysis_status(self, news_item_id, status, signal_id=None) -> NewsItem:
        raise NotImplementedError


def _instrument() -> Instrument:
    return Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        asset_class=AssetClass.STOCK,
        currency="USD",
    )


def _news_item() -> NewsItem:
    return NewsItem(
        id="abc",
        title="Apple beats earnings",
        summary="Apple reported record quarterly revenue.",
        url="https://example.com/apple",
        source="Reuters",
        provider="finnhub",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def _build(
    runner: AgentRunner, universe: InstrumentUniverse, news: NewsItemRepository
) -> StreamReply:
    return StreamReply(
        agent_runner=runner,
        instrument_universe=universe,
        news_item_repository=news,
    )


async def _drain(stream: AsyncIterator[AgentStreamEvent]) -> list[AgentStreamEvent]:
    return [event async for event in stream]


async def test_asset_symbol_resolves_to_grounding_context() -> None:
    runner = _FakeAgentRunner()
    use_case = _build(
        runner,
        _FakeInstrumentUniverse(_instrument()),
        _FakeNewsItemRepository(None),
    )

    await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            asset_symbol="AAPL",
        )
    )

    assert runner.called
    assert runner.grounding_context is not None
    assert "AAPL" in runner.grounding_context
    assert "Apple Inc." in runner.grounding_context


async def test_news_id_resolves_to_grounding_context() -> None:
    runner = _FakeAgentRunner()
    use_case = _build(
        runner,
        _FakeInstrumentUniverse(None),
        _FakeNewsItemRepository(_news_item()),
    )

    await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            news_id="abc",
        )
    )

    assert runner.grounding_context is not None
    assert "Apple beats earnings" in runner.grounding_context


async def test_no_reference_leaves_grounding_context_none() -> None:
    runner = _FakeAgentRunner()
    use_case = _build(
        runner,
        _FakeInstrumentUniverse(_instrument()),
        _FakeNewsItemRepository(_news_item()),
    )

    await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
        )
    )

    assert runner.called
    assert runner.grounding_context is None


async def test_unknown_symbol_leaves_grounding_context_none() -> None:
    runner = _FakeAgentRunner()
    use_case = _build(
        runner,
        _FakeInstrumentUniverse(None),
        _FakeNewsItemRepository(None),
    )

    await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            asset_symbol="ZZZZ",
        )
    )

    assert runner.grounding_context is None


async def test_unknown_news_id_leaves_grounding_context_none() -> None:
    runner = _FakeAgentRunner()
    use_case = _build(
        runner,
        _FakeInstrumentUniverse(None),
        _FakeNewsItemRepository(None),
    )

    await _drain(
        use_case.execute(
            "thread-1",
            Message(role=MessageRole.USER, content="hi"),
            "user-1",
            news_id="does-not-exist",
        )
    )

    assert runner.grounding_context is None
