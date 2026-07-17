"""Routing cover for `BroadcastImportantEvents`' hybrid delivery.

An event that clears the "notify at all" gate (`should_notify` + `importance_threshold`) is then
ROUTED: at/above `broadcast_importance_threshold` it is broadcast market-wide; below it, it is
delivered only to users whose watchlist tracks one of its affected assets. These tests drive the
real `execute()` (via fake ports) and assert exactly which delivery method each event triggers.

Per `backend/CLAUDE.md`: a minimal targeted test next to the behavior under test, not the start of
a broad suite.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from app.application.event_intelligence.processed_event_tracker import ProcessedEventTracker
from app.application.event_intelligence.use_cases import BroadcastImportantEvents
from app.application.event_intelligence.use_cases.process_incoming_event import ProcessIncomingEvent
from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.domain.event_intelligence.ports import (
    EventAnalyzerPort,
    EventRepositoryPort,
    NewsProviderPort,
)
from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse
from app.domain.notification.entities import (
    Alert,
    BriefingReadyNotification,
    ScenarioArmedNotification,
    ScenarioMatchNotification,
)
from app.domain.notification.ports import NotificationChannel
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository


def _news(title: str) -> NewsEvent:
    return NewsEvent(title=title, description="d", content="c", source="test")


def _enriched(event_id: str, title: str, *, importance: float, assets: list[str]) -> EnrichedEvent:
    return EnrichedEvent(
        id=event_id,
        original=_news(title),
        summary="s",
        importance=importance,
        should_notify=True,
        affected_assets=assets,
        affected_sectors=[],
        confidence=0.9,
        reasoning="r",
        suggested_questions=[],
        analyzed_at=datetime.now(UTC),
    )


class _FakeNewsProvider(NewsProviderPort):
    def __init__(self, events: list[NewsEvent]) -> None:
        self._events = events

    async def fetch_latest_news(self) -> list[NewsEvent]:
        return list(self._events)


class _MappingAnalyzer(EventAnalyzerPort):
    """Returns a pre-baked `EnrichedEvent` per news title — stands in for Gemini.

    Records every title it was asked to analyze in `analyzed_titles`, so a test can assert that an
    article dropped by the relevance pre-gate never reached (never billed) the analyzer.
    """

    def __init__(self, analysis: dict[str, EnrichedEvent]) -> None:
        self._analysis = analysis
        self.analyzed_titles: list[str] = []
        # Every asset `analyze_impact` was asked about — a test asserts this is once per asset, not
        # once per user watching it (impact text is cached per-(event, asset)).
        self.impact_calls: list[str] = []

    async def analyze(self, event: NewsEvent) -> EnrichedEvent:
        self.analyzed_titles.append(event.title)
        return self._analysis[event.title]

    async def analyze_impact(self, event: EnrichedEvent, sector: str) -> str:
        # Param name mirrors the port (`sector`), though the Sentinel path passes an asset symbol.
        self.impact_calls.append(sector)
        return f"Impacto en {sector}"


class _InMemoryEventRepository(EventRepositoryPort):
    def __init__(self) -> None:
        self._events: list[EnrichedEvent] = []

    async def save(self, event: EnrichedEvent) -> None:
        self._events.append(event)

    async def list_all(self) -> list[EnrichedEvent]:
        return list(self._events)

    async def get(self, event_id: str) -> EnrichedEvent | None:
        return next((e for e in self._events if e.id == event_id), None)


class _RecordingChannel(NotificationChannel):
    """Records which delivery method each event went through."""

    def __init__(self) -> None:
        self.broadcasts: list[str] = []
        # (event_id, user_id, tuple(watched_symbols)) — the third slot lets a test assert each
        # user was told exactly which of THEIR tracked assets the event affects.
        self.per_user: list[tuple[str, str, tuple[str, ...]]] = []
        # The per-asset impact map handed to each send — a test asserts every user shares the same
        # (cached) map instance's contents rather than a per-user recomputation.
        self.impacts_seen: list[dict[str, str]] = []

    async def send(self, alert: Alert) -> None:
        raise NotImplementedError

    async def send_briefing_ready(self, notification: BriefingReadyNotification) -> None:
        raise NotImplementedError

    async def send_scenario_match(self, notification: ScenarioMatchNotification) -> None:
        raise NotImplementedError

    async def send_scenario_armed(self, notification: ScenarioArmedNotification) -> None:
        raise NotImplementedError

    async def broadcast_event_alert(self, event: EnrichedEvent) -> None:
        self.broadcasts.append(event.id)

    async def send_event_alert_to_user(
        self,
        event: EnrichedEvent,
        user_id: str,
        watched_symbols: Sequence[str],
        asset_impacts: Mapping[str, str],
    ) -> None:
        self.per_user.append((event.id, user_id, tuple(watched_symbols)))
        self.impacts_seen.append(dict(asset_impacts))


class _FakeWatchlistRepo(WatchlistRepository):
    """Only `list_user_ids_tracking` is exercised; the rest guard against accidental use."""

    def __init__(self, symbol_to_users: dict[str, set[str]]) -> None:
        self._map = symbol_to_users
        self.lookups: list[set[str]] = []

    async def list_user_ids_tracking(self, symbols: Sequence[str]) -> set[str]:
        received = {symbol.upper() for symbol in symbols}
        self.lookups.append(received)
        result: set[str] = set()
        for symbol in received:
            result |= self._map.get(symbol, set())
        return result

    async def list_trackers_by_symbol(self, symbols: Sequence[str]) -> dict[str, set[str]]:
        received = {symbol.upper() for symbol in symbols}
        self.lookups.append(received)
        return {
            symbol: set(self._map[symbol])
            for symbol in received
            if symbol in self._map and self._map[symbol]
        }

    async def list_all_tracked_symbols(self) -> set[str]:
        # A symbol is "tracked" iff some user tracks it — i.e. the keys of the reverse map.
        return {symbol.upper() for symbol in self._map}

    async def create(self, watchlist: Watchlist) -> Watchlist:
        raise NotImplementedError

    async def get(self, watchlist_id: str) -> Watchlist | None:
        raise NotImplementedError

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        raise NotImplementedError

    async def list_all(self) -> list[Watchlist]:
        raise NotImplementedError

    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        raise NotImplementedError

    async def reorder(self, user_id: str, ordered_ids: list[str]) -> None:
        raise NotImplementedError

    async def delete(self, watchlist_id: str) -> None:
        raise NotImplementedError

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        raise NotImplementedError

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        raise NotImplementedError

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        raise NotImplementedError


class _FakeUniverse(InstrumentUniverse):
    def __init__(self, known_symbols: list[str]) -> None:
        self._by_symbol = {
            symbol.upper(): Instrument(
                symbol=symbol.upper(), name=symbol, asset_class=AssetClass.STOCK, currency="USD"
            )
            for symbol in known_symbols
        }

    def all(self) -> list[Instrument]:
        return list(self._by_symbol.values())

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol.upper())

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [i for i in self._by_symbol.values() if i.asset_class == asset_class]


def _build(
    *,
    news_events: list[NewsEvent],
    analysis: dict[str, EnrichedEvent],
    channel: _RecordingChannel,
    watchlist: _FakeWatchlistRepo,
    universe: _FakeUniverse,
    analyzer: _MappingAnalyzer | None = None,
    broadcast_floor: float = 0.90,
    macro_keywords: Sequence[str] = ("recession", "inflation", "Federal Reserve"),
) -> BroadcastImportantEvents:
    # One analyzer instance behind BOTH the analyze pipeline and the impact blurbs, so a test can
    # assert impact-call counts on the same object the use case actually calls.
    analyzer = analyzer or _MappingAnalyzer(analysis)
    return BroadcastImportantEvents(
        news_provider=_FakeNewsProvider(news_events),
        process_incoming_event=ProcessIncomingEvent(
            analyzer=analyzer, repository=_InMemoryEventRepository()
        ),
        notification_channel=channel,
        processed_event_tracker=ProcessedEventTracker(),
        watchlist_repository=watchlist,
        instrument_universe=universe,
        event_analyzer=analyzer,
        importance_threshold=0.7,
        broadcast_importance_threshold=broadcast_floor,
        max_alerts_per_run=3,
        max_concurrency=3,
        macro_keywords=macro_keywords,
        min_symbol_match_length=3,
    )


async def test_high_importance_event_is_broadcast_market_wide_not_per_user() -> None:
    # Raw title mentions BTC so it clears the relevance pre-gate (a user tracks BTC).
    news = _news("BTC surges to a record high")
    enriched = _enriched("e-high", news.title, importance=0.95, assets=["BTC"])
    channel = _RecordingChannel()
    # A user DOES track BTC, but the broadcast path must not even consult the watchlist.
    watchlist = _FakeWatchlistRepo({"BTC": {"u1"}})

    routed = await _build(
        news_events=[news],
        analysis={news.title: enriched},
        channel=channel,
        watchlist=watchlist,
        universe=_FakeUniverse(["BTC"]),
    ).execute()

    assert [event.id for event in routed] == ["e-high"]
    assert channel.broadcasts == ["e-high"]
    assert channel.per_user == []
    assert watchlist.lookups == []  # broadcast path never does the reverse lookup


async def test_mid_importance_event_targets_only_watchlist_tracking_users() -> None:
    # Raw title mentions AAPL so it clears the relevance pre-gate (users track AAPL).
    news = _news("AAPL posts notable results")
    # Free-form "aapl" normalizes to canonical "AAPL" via the universe.
    enriched = _enriched("e-mid", news.title, importance=0.80, assets=["aapl"])
    channel = _RecordingChannel()
    watchlist = _FakeWatchlistRepo({"AAPL": {"u1", "u2"}})

    routed = await _build(
        news_events=[news],
        analysis={news.title: enriched},
        channel=channel,
        watchlist=watchlist,
        universe=_FakeUniverse(["AAPL"]),
    ).execute()

    assert [event.id for event in routed] == ["e-mid"]
    assert channel.broadcasts == []
    assert watchlist.lookups == [{"AAPL"}]
    assert [event_id for event_id, _user, _watched in channel.per_user] == ["e-mid", "e-mid"]
    assert {user_id for _event, user_id, _watched in channel.per_user} == {"u1", "u2"}
    # Both recipients track only AAPL, so each is told exactly that.
    assert {watched for _event, _user, watched in channel.per_user} == {("AAPL",)}


async def test_mid_importance_event_with_no_watchlist_match_reaches_nobody() -> None:
    # Nobody tracks its asset, but the raw title hits a MACRO keyword so it still clears the
    # relevance pre-gate and gets analyzed — the "reaches nobody" is a ROUTING outcome, not a gate.
    news = _news("recession fears mount across markets")
    enriched = _enriched("e-none", news.title, importance=0.80, assets=["ZZZ"])
    channel = _RecordingChannel()
    watchlist = _FakeWatchlistRepo({})  # nobody tracks anything

    routed = await _build(
        news_events=[news],
        analysis={news.title: enriched},
        channel=channel,
        watchlist=watchlist,
        universe=_FakeUniverse([]),
    ).execute()

    assert [event.id for event in routed] == ["e-none"]
    assert channel.broadcasts == []
    assert channel.per_user == []


async def test_irrelevant_article_is_dropped_before_any_ai_call() -> None:
    # Two fresh articles reach the scan; only the one mentioning a watchlisted symbol is relevant.
    # The off-topic one must be dropped by the pre-gate BEFORE the (billed) Gemini analyze step.
    relevant = _news("BTC breaks out to new highs")
    irrelevant = _news("local bakery wins a pie contest")
    channel = _RecordingChannel()
    watchlist = _FakeWatchlistRepo({"BTC": {"u1"}})
    # Only the relevant title is in the analyzer's map — if the gate let the irrelevant one
    # through, `analyzed_titles` would record it (the KeyError is swallowed by `_analyze_all`).
    analyzer = _MappingAnalyzer(
        {relevant.title: _enriched("e-rel", relevant.title, importance=0.95, assets=["BTC"])}
    )
    use_case = BroadcastImportantEvents(
        news_provider=_FakeNewsProvider([relevant, irrelevant]),
        process_incoming_event=ProcessIncomingEvent(
            analyzer=analyzer, repository=_InMemoryEventRepository()
        ),
        notification_channel=channel,
        processed_event_tracker=ProcessedEventTracker(),
        watchlist_repository=watchlist,
        instrument_universe=_FakeUniverse(["BTC"]),
        event_analyzer=analyzer,
        importance_threshold=0.7,
        broadcast_importance_threshold=0.90,
        max_alerts_per_run=3,
        max_concurrency=3,
        macro_keywords=["recession"],
        min_symbol_match_length=3,
    )

    routed = await use_case.execute()

    assert analyzer.analyzed_titles == ["BTC breaks out to new highs"]
    assert [event.id for event in routed] == ["e-rel"]
    assert channel.broadcasts == ["e-rel"]


async def test_targeted_event_personalizes_per_user_and_caches_impact_per_asset() -> None:
    # user1 tracks only AAPL; user2 tracks AAPL + MSFT. The raw title mentions both, so the event
    # clears the relevance pre-gate; importance 0.80 is below the 0.90 broadcast floor -> targeted.
    news = _news("AAPL and MSFT slide on guidance")
    enriched = _enriched("e-mid", news.title, importance=0.80, assets=["AAPL", "MSFT"])
    channel = _RecordingChannel()
    watchlist = _FakeWatchlistRepo({"AAPL": {"u1", "u2"}, "MSFT": {"u2"}})
    analyzer = _MappingAnalyzer({news.title: enriched})

    routed = await _build(
        news_events=[news],
        analysis={news.title: enriched},
        channel=channel,
        watchlist=watchlist,
        universe=_FakeUniverse(["AAPL", "MSFT"]),
        analyzer=analyzer,
    ).execute()

    assert [event.id for event in routed] == ["e-mid"]
    assert channel.broadcasts == []

    # Each user is told exactly which of THEIR tracked assets the event affects.
    matched = {user_id: set(watched) for _eid, user_id, watched in channel.per_user}
    assert matched == {"u1": {"AAPL"}, "u2": {"AAPL", "MSFT"}}

    # analyze_impact runs ONCE per affected asset someone watches (AAPL, MSFT) — never per user,
    # even though two users both watch AAPL.
    assert sorted(analyzer.impact_calls) == ["AAPL", "MSFT"]

    # Every recipient shares the one cached per-asset impact map.
    assert channel.impacts_seen == [
        {"AAPL": "Impacto en AAPL", "MSFT": "Impacto en MSFT"},
        {"AAPL": "Impacto en AAPL", "MSFT": "Impacto en MSFT"},
    ]
