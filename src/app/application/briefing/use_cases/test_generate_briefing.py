"""Regression test for the `open_review_items` "openness" bug (issue #16 follow-up).

Prior behavior treated ANY recorded review state as closing an item — including a
single `ESCALATED` state, even though `review_transition_policy` explicitly defines
`ESCALATED` as non-terminal. That silently dropped escalated-but-unresolved items
from `open_review_items`, the opposite of what escalation exists for.

Per `backend/CLAUDE.md`: "No tests during the hackathon... If a bug needs a
regression test mid-hackathon, add a minimal pytest test next to the code under
test" — this is that minimal test, not the start of a suite.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.application.briefing.use_cases.generate_briefing import GenerateBriefing
from app.domain.agents.entities import Message
from app.domain.agents.ports import LLMProvider
from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository
from app.domain.review.entities import ReviewDecision, ReviewedEntityType, ReviewState
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository


class _UnusedWatchlistRepository(WatchlistRepository):
    """Satisfies the constructor; `_gather_open_review_items` never touches this port."""

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

    async def delete(self, watchlist_id: str) -> None:
        raise NotImplementedError

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        raise NotImplementedError

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        raise NotImplementedError

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        raise NotImplementedError


class _UnusedLLMProvider(LLMProvider):
    """Satisfies the constructor; `_gather_open_review_items` never touches this port."""

    async def complete(self, messages: list[Message]) -> str:
        raise NotImplementedError

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""  # pragma: no cover

    async def complete_structured(
        self, messages: list[Message], schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        raise NotImplementedError


class _FakeSignalRepository(SignalRepository):
    """In-memory `SignalRepository` fake: `review_states` maps signal id -> its audit
    trail, oldest first (matching the real port's "most recent last" contract)."""

    def __init__(self, review_states: dict[str, list[ReviewState]]) -> None:
        self._review_states = review_states

    async def create(self, signal: Signal) -> Signal:
        raise NotImplementedError

    async def get(self, signal_id: str) -> Signal | None:
        raise NotImplementedError

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        raise NotImplementedError

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        return self._review_states.get(signal_id, [])


class _FakeBriefingRepository(BriefingRepository):
    """In-memory `BriefingRepository` fake, same shape as `_FakeSignalRepository`."""

    def __init__(
        self, briefings: list[Briefing], review_states: dict[str, list[ReviewState]]
    ) -> None:
        self._briefings = briefings
        self._review_states = review_states

    async def create(self, briefing: Briefing) -> Briefing:
        raise NotImplementedError

    async def get(self, briefing_id: str) -> Briefing | None:
        raise NotImplementedError

    async def list_for_watchlist(self, watchlist_id: str) -> list[Briefing]:
        return self._briefings

    async def get_latest_for_watchlist(self, watchlist_id: str) -> Briefing | None:
        return max(self._briefings, key=lambda b: b.created_at) if self._briefings else None

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        return self._review_states.get(briefing_id, [])


def _signal(signal_id: str) -> Signal:
    return Signal(
        id=signal_id,
        instrument_symbol="AAPL",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.8,
        evidence=[],
        disclaimer="not personalized advice",
    )


def _briefing(briefing_id: str, watchlist_id: str) -> Briefing:
    return Briefing(
        id=briefing_id,
        watchlist_id=watchlist_id,
        summary="prior briefing",
        disclaimer="not personalized advice",
    )


def _review_state(decision: ReviewDecision, entity_type: ReviewedEntityType) -> ReviewState:
    return ReviewState(
        id=f"review-{decision.value}",
        entity_type=entity_type,
        entity_id="unused",
        user_id="reviewer-1",
        decision=decision,
        justification="justification",
        created_at=datetime.now(UTC),
    )


def _make_use_case(
    signal_repository: SignalRepository, briefing_repository: BriefingRepository
) -> GenerateBriefing:
    return GenerateBriefing(
        watchlist_repository=_UnusedWatchlistRepository(),
        signal_repository=signal_repository,
        briefing_repository=briefing_repository,
        llm_provider=_UnusedLLMProvider(),
    )


async def test_signal_with_no_review_states_is_open() -> None:
    signal = _signal("sig-none")
    use_case = _make_use_case(
        signal_repository=_FakeSignalRepository({}),
        briefing_repository=_FakeBriefingRepository([], {}),
    )

    open_items = await use_case._gather_open_review_items("wl-1", [signal])

    assert [item.entity_id for item in open_items] == ["sig-none"]


async def test_signal_with_only_escalated_state_is_open() -> None:
    """The confirmed bug: an ESCALATED-only item must NOT be treated as closed."""
    signal = _signal("sig-escalated")
    states = {
        "sig-escalated": [
            _review_state(ReviewDecision.ESCALATED, ReviewedEntityType.SIGNAL),
        ]
    }
    use_case = _make_use_case(
        signal_repository=_FakeSignalRepository(states),
        briefing_repository=_FakeBriefingRepository([], {}),
    )

    open_items = await use_case._gather_open_review_items("wl-1", [signal])

    assert [item.entity_id for item in open_items] == ["sig-escalated"]


async def test_signal_with_terminal_state_is_closed() -> None:
    for terminal_decision in (ReviewDecision.REVIEWED, ReviewDecision.DISCARDED):
        signal = _signal(f"sig-{terminal_decision.value}")
        states = {
            signal.id: [_review_state(terminal_decision, ReviewedEntityType.SIGNAL)],
        }
        use_case = _make_use_case(
            signal_repository=_FakeSignalRepository(states),
            briefing_repository=_FakeBriefingRepository([], {}),
        )

        open_items = await use_case._gather_open_review_items("wl-1", [signal])

        assert open_items == [], (
            f"expected {terminal_decision} to close the item, but it stayed open"
        )


async def test_signal_escalated_then_reviewed_is_closed_by_latest_decision() -> None:
    """Multiple review states: openness must follow the LATEST decision, not the first."""
    signal = _signal("sig-esc-then-reviewed")
    escalated = _review_state(ReviewDecision.ESCALATED, ReviewedEntityType.SIGNAL)
    reviewed = _review_state(ReviewDecision.REVIEWED, ReviewedEntityType.SIGNAL)
    # `list_review_states` is documented "most recent last" — the later `REVIEWED`
    # decision must be the one that determines openness, not the earlier `ESCALATED`.
    states = {signal.id: [escalated, reviewed]}
    use_case = _make_use_case(
        signal_repository=_FakeSignalRepository(states),
        briefing_repository=_FakeBriefingRepository([], {}),
    )

    open_items = await use_case._gather_open_review_items("wl-1", [signal])

    assert open_items == []


async def test_briefing_open_review_items_follow_the_same_latest_decision_rule() -> None:
    """The fix applies identically to prior briefings, not just signals."""
    open_briefing = _briefing("brief-escalated", "wl-1")
    closed_briefing = _briefing("brief-reviewed", "wl-1")
    states = {
        "brief-escalated": [_review_state(ReviewDecision.ESCALATED, ReviewedEntityType.BRIEFING)],
        "brief-reviewed": [_review_state(ReviewDecision.REVIEWED, ReviewedEntityType.BRIEFING)],
    }
    use_case = _make_use_case(
        signal_repository=_FakeSignalRepository({}),
        briefing_repository=_FakeBriefingRepository([open_briefing, closed_briefing], states),
    )

    open_items = await use_case._gather_open_review_items("wl-1", [])

    assert [item.entity_id for item in open_items] == ["brief-escalated"]
