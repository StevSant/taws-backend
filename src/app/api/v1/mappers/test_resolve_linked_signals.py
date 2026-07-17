"""Unit tests for `resolve_linked_signals` batching and its resolution ladder.

Contracts pinned here:
- exactly ONE `get_by_ids` batch call (never a per-id `get()` loop);
- a repository hit resolves fully (symbol/impact/confidence/title from the signal);
- a repository miss whose id appears in the briefing's `instrument_breakdown`
  degrades to a partial row carrying the section's real symbol;
- an id in neither place falls back to the existing "—" missing sentinel;
- output order mirrors the input id order.
"""

from collections.abc import Sequence

from app.api.v1.mappers import resolve_linked_signals
from app.domain.briefing.entities import BriefingInstrumentSection
from app.domain.review.entities import ReviewState
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.signals.ports import SignalRepository


class _BatchOnlySignalRepository(SignalRepository):
    """`get_by_ids` serves canned signals; single-id `get` fails the test if called."""

    def __init__(self, known: dict[str, Signal]) -> None:
        self._known = known
        self.batch_calls: list[list[str]] = []

    async def create(self, signal: Signal) -> Signal:
        raise NotImplementedError

    async def get(self, signal_id: str) -> Signal | None:
        raise AssertionError("resolve_linked_signals must use get_by_ids, not per-id get()")

    async def get_by_ids(self, signal_ids: Sequence[str]) -> dict[str, Signal]:
        self.batch_calls.append(list(signal_ids))
        return {
            signal_id: self._known[signal_id]
            for signal_id in signal_ids
            if signal_id in self._known
        }

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        raise NotImplementedError

    async def get_latest_for_instrument(self, symbol: str, locale: str) -> Signal | None:
        raise NotImplementedError

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        raise NotImplementedError

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        raise NotImplementedError


def _known_signal() -> Signal:
    return Signal(
        id="sig-known",
        instrument_symbol="AAPL",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.82,
        evidence=[],
        disclaimer="not personalized advice",
        thesis="Apple momentum builds into earnings.",
    )


_BREAKDOWN = [
    BriefingInstrumentSection(symbol="MSFT", narrative="n", signal_ids=["sig-pruned"]),
]


async def test_resolves_via_one_batch_call_with_breakdown_and_sentinel_fallbacks() -> None:
    repository = _BatchOnlySignalRepository({"sig-known": _known_signal()})

    resolved = await resolve_linked_signals(
        ["sig-known", "sig-pruned", "sig-gone"], repository, _BREAKDOWN
    )

    assert repository.batch_calls == [["sig-known", "sig-pruned", "sig-gone"]]

    assert [item.signal_id for item in resolved] == ["sig-known", "sig-pruned", "sig-gone"]

    known = resolved[0]
    assert known.symbol == "AAPL"
    assert known.impact == ImpactClass.POSITIVE.value
    assert known.confidence == 0.82
    assert known.title == "Apple momentum builds into earnings."

    pruned = resolved[1]
    assert pruned.symbol == "MSFT"
    assert pruned.impact == ImpactClass.UNCERTAIN.value
    assert pruned.confidence == 0.0
    assert pruned.title == ""

    gone = resolved[2]
    assert gone.symbol == "—"
    assert gone.confidence == 0.0


async def test_empty_ids_resolve_to_empty_list_without_a_batch_call() -> None:
    repository = _BatchOnlySignalRepository({})

    resolved = await resolve_linked_signals([], repository, _BREAKDOWN)

    assert resolved == []
    assert repository.batch_calls == []
