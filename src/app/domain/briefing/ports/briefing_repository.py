from abc import ABC, abstractmethod

from app.domain.briefing.entities import Briefing
from app.domain.review.entities import ReviewState


class BriefingRepository(ABC):
    """Port for persisting Advisor-agent briefings and their review states.

    `save_review_state`/`list_review_states` are the primitive persistence methods the
    review *use case* (issue #4) will call — the transition workflow itself (allowed
    state changes, authorization) is out of scope for this port.
    """

    @abstractmethod
    async def create(self, briefing: Briefing) -> Briefing:
        """Create a new briefing and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, briefing_id: str) -> Briefing | None:
        """Return the briefing with this id, or `None` if it doesn't exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_watchlist(self, watchlist_id: str) -> list[Briefing]:
        """Return every briefing recorded for the given watchlist."""
        raise NotImplementedError

    @abstractmethod
    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        """Persist a reviewer decision (reviewed/escalated/discarded) on a briefing.

        May raise `IllegalReviewTransitionError` (`app.domain.review`) if the
        underlying store's transition-safety trigger rejects the insert — a
        DB-level backstop against a concurrent-request race on the same briefing, in
        addition to (not instead of) the use case's own pre-insert check.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        """Return the full review audit trail for a briefing, most recent last."""
        raise NotImplementedError
