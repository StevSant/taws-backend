from abc import ABC, abstractmethod

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
    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        """Return every signal recorded for the given instrument symbol."""
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
