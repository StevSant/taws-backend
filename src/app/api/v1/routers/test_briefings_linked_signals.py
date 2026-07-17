"""Endpoint test for the linked-signal enrichment on the briefings routes.

`BriefingResponse` historically exposed only `linked_signal_ids` (raw UUIDs). The
frontend renders each linked signal as a link to `/radar/{symbol}`, so it needs the
resolved `symbol`, `impact`, `confidence`, and a short `title`. This drives the real
`GET /api/v1/watchlists/{id}/briefings` route via `TestClient` with DI overrides and
covers the two contracts the frontend relies on:

- a linked id that resolves -> a `LinkedSignalResponse` carrying the signal's symbol,
  impact, confidence, and thesis title;
- a linked id that no longer resolves but is still listed by an
  `instrument_breakdown` section (retention pruned the row) -> a partial row with
  the section's real symbol and neutral impact/confidence;
- a linked id in neither place -> a degraded placeholder row (id preserved, "—"
  symbol) instead of a crash or a dropped id.

Per `backend/CLAUDE.md`: a minimal targeted test next to the behavior under test, not
the start of a broad suite.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.v1.dependencies import (
    get_briefing_repository,
    get_signal_repository,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser
from app.domain.briefing.entities import Briefing, BriefingInstrumentSection
from app.domain.review.entities import ReviewState
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
from app.main import app

_USER_ID = "dev-user"
_WATCHLIST_ID = "wl-1"
_KNOWN_SIGNAL_ID = "sig-known"
_PRUNED_SIGNAL_ID = "sig-pruned"
_MISSING_SIGNAL_ID = "sig-missing"


class _StubSignalRepository(SignalRepository):
    """`get_by_ids` serves canned signals; ids it doesn't know are simply absent."""

    def __init__(self, known: dict[str, Signal]) -> None:
        self._known = known

    async def create(self, signal: Signal) -> Signal:
        raise NotImplementedError

    async def get(self, signal_id: str) -> Signal | None:
        return self._known.get(signal_id)

    async def get_by_ids(self, signal_ids: Sequence[str]) -> dict[str, Signal]:
        return {
            signal_id: self._known[signal_id]
            for signal_id in signal_ids
            if signal_id in self._known
        }

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        raise NotImplementedError

    async def get_latest_for_instrument(self, symbol: str, locale: str) -> Signal | None:
        return None

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        return 0

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        return []


class _StubBriefingRepository:
    """Only `list_for_watchlist` is exercised by the GET list route."""

    def __init__(self, briefings: list[Briefing]) -> None:
        self._briefings = briefings

    async def create(self, briefing: Briefing) -> Briefing:
        raise NotImplementedError

    async def get(self, briefing_id: str) -> Briefing | None:
        raise NotImplementedError

    async def list_for_watchlist(self, watchlist_id: str) -> list[Briefing]:
        return self._briefings

    async def get_latest_for_watchlist(self, watchlist_id: str) -> Briefing | None:
        raise NotImplementedError

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        return []


class _StubWatchlistRepository(WatchlistRepository):
    """Only `get` is exercised, by the ownership check on the briefings route."""

    def __init__(self, watchlist: Watchlist) -> None:
        self._watchlist = watchlist

    async def create(self, watchlist: Watchlist) -> Watchlist:
        raise NotImplementedError

    async def get(self, watchlist_id: str) -> Watchlist | None:
        return self._watchlist if watchlist_id == self._watchlist.id else None

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


def _known_signal() -> Signal:
    return Signal(
        id=_KNOWN_SIGNAL_ID,
        instrument_symbol="AAPL",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.82,
        evidence=[],
        disclaimer="not personalized advice",
        thesis="Apple momentum builds into earnings.",
    )


def _briefing_with_linked_ids() -> Briefing:
    return Briefing(
        id="brief-1",
        watchlist_id=_WATCHLIST_ID,
        summary="summary",
        disclaimer="not personalized advice",
        linked_signal_ids=[_KNOWN_SIGNAL_ID, _PRUNED_SIGNAL_ID, _MISSING_SIGNAL_ID],
        instrument_breakdown=[
            BriefingInstrumentSection(symbol="MSFT", narrative="n", signal_ids=[_PRUNED_SIGNAL_ID]),
        ],
        created_at=datetime.now(UTC),
    )


def _override_dependencies() -> None:
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="dev@example.com"
    )
    watchlist = Watchlist(id=_WATCHLIST_ID, user_id=_USER_ID, name="wl")
    app.dependency_overrides[get_watchlist_repository] = lambda: _StubWatchlistRepository(watchlist)
    app.dependency_overrides[get_briefing_repository] = lambda: _StubBriefingRepository(
        [_briefing_with_linked_ids()]
    )
    app.dependency_overrides[get_signal_repository] = lambda: _StubSignalRepository(
        {_KNOWN_SIGNAL_ID: _known_signal()}
    )


def test_list_briefings_enriches_linked_signals_and_degrades_for_missing_id() -> None:
    _override_dependencies()
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/watchlists/{_WATCHLIST_ID}/briefings")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    briefing = body[0]

    # Backward-compatible raw ids are preserved.
    assert briefing["linked_signal_ids"] == [
        _KNOWN_SIGNAL_ID,
        _PRUNED_SIGNAL_ID,
        _MISSING_SIGNAL_ID,
    ]

    linked = briefing["linked_signals"]
    assert len(linked) == 3

    known = linked[0]
    assert known["signal_id"] == _KNOWN_SIGNAL_ID
    assert known["symbol"] == "AAPL"
    assert known["impact"] == ImpactClass.POSITIVE.value
    assert known["confidence"] == 0.82
    assert known["title"] == "Apple momentum builds into earnings."

    # Pruned id: repository miss, but its breakdown section still knows the symbol.
    pruned = linked[1]
    assert pruned["signal_id"] == _PRUNED_SIGNAL_ID
    assert pruned["symbol"] == "MSFT"
    assert pruned["impact"] == ImpactClass.UNCERTAIN.value
    assert pruned["confidence"] == 0.0
    assert pruned["title"] == ""

    # An id in neither place degrades gracefully instead of crashing or being dropped.
    missing = linked[2]
    assert missing["signal_id"] == _MISSING_SIGNAL_ID
    assert missing["symbol"] == "—"
    assert missing["confidence"] == 0.0
