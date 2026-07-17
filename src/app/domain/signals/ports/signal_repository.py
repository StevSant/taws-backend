from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.domain.review.entities import ReviewState
from app.domain.signals.entities import Signal


class SignalRepository(ABC):
    """Port for persisting Analyst-agent signals and their review states.

    `save_review_state`/`list_review_states` are the primitive persistence methods the
    review *use case* (issue #4) will call — the transition workflow itself (allowed
    state changes, authorization) is out of scope for this port.
    """

    @abstractmethod
    async def create(self, signal: Signal) -> Signal:
        """Create a new signal and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, signal_id: str) -> Signal | None:
        """Return the signal with this id, or `None` if it doesn't exist."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_ids(self, signal_ids: Sequence[str]) -> dict[str, Signal]:
        """Return the signals found for `signal_ids`, keyed by id.

        Batch companion to `get(...)` for the briefing read/export paths, which
        resolve every signal id a briefing references — N ids must cost one query,
        not N. Missing ids (pruned by retention, deleted) are simply absent from
        the result — never an exception — and empty input returns an empty dict.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        """Return every signal recorded for the given instrument symbol."""
        raise NotImplementedError

    @abstractmethod
    async def get_latest_for_instrument(self, symbol: str, locale: str) -> Signal | None:
        """Return the newest signal for `(symbol, locale)`, or `None` if there is none.

        The freshness-cache lookup (issue #29) and the "latest signal" read path. A single
        `order by created_at desc limit 1` — deliberately NOT `list_for_instrument(...)` +
        `max(...)` in the caller, which pulls every historical row over the wire just to
        throw all but one away.

        `locale` is part of the key because a `Signal`'s analytical fields are localized;
        see `Signal.locale`.
        """
        raise NotImplementedError

    @abstractmethod
    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        """Delete all but the `keep` newest signals for `(symbol, locale)`; return how many
        rows were deleted.

        Retention (issue #29): without this, `signals` grows unboundedly with near-duplicate
        rows since readers only ever look at the newest. Pruning the source rows is safe —
        `historical_analogs` holds its own separately-indexed copy of the RAG corpus.
        """
        raise NotImplementedError

    @abstractmethod
    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        """Persist a reviewer decision (reviewed/escalated/discarded) on a signal.

        May raise `IllegalReviewTransitionError` (`app.domain.review`) if the
        underlying store's transition-safety trigger rejects the insert — a
        DB-level backstop against a concurrent-request race on the same signal, in
        addition to (not instead of) the use case's own pre-insert check.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        """Return the full review audit trail for a signal, most recent last."""
        raise NotImplementedError
