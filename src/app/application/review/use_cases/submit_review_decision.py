import uuid

from app.application.review.review_target_not_found_error import ReviewTargetNotFoundError
from app.application.review.review_transition_policy import assert_transition_allowed
from app.domain.briefing.ports import BriefingRepository
from app.domain.review.entities import ReviewDecision, ReviewedEntityType, ReviewState
from app.domain.signals.ports import SignalRepository


class SubmitReviewDecision:
    """Validates and persists one reviewer decision on a signal or briefing.

    Depends only on the `SignalRepository`/`BriefingRepository` ports — constructor
    injection keeps this use case unaware of Supabase or any other adapter. Given
    `entity_type`, `entity_id`, `user_id`, `decision`, and `justification`, it:

    1. Verifies the target entity exists (via `get()` on the right repository) —
       raises `ReviewTargetNotFoundError` if not.
    2. Fetches the entity's existing review states (via `list_review_states()`) to
       determine its current latest decision, if any.
    3. Validates the requested decision is a legal transition from that latest
       decision, per `review_transition_policy.assert_transition_allowed` — raises
       `IllegalReviewTransitionError` if not.
    4. Persists a brand-new `ReviewState` row (via `save_review_state()`) — review
       states are append-only, so this never mutates a prior row.

    Escalation is just `ReviewDecision.ESCALATED` on this same `ReviewState` row —
    there is no separate alert/task record and no trade/execution side effect.
    """

    def __init__(
        self, signal_repository: SignalRepository, briefing_repository: BriefingRepository
    ) -> None:
        self._signal_repository = signal_repository
        self._briefing_repository = briefing_repository

    async def execute(
        self,
        entity_type: ReviewedEntityType,
        entity_id: str,
        user_id: str,
        decision: ReviewDecision,
        justification: str,
    ) -> ReviewState:
        if entity_type is ReviewedEntityType.SIGNAL:
            entity_exists = await self._signal_repository.get(entity_id) is not None
            existing_states = await self._signal_repository.list_review_states(entity_id)
        else:
            entity_exists = await self._briefing_repository.get(entity_id) is not None
            existing_states = await self._briefing_repository.list_review_states(entity_id)

        if not entity_exists:
            raise ReviewTargetNotFoundError(entity_type=entity_type, entity_id=entity_id)

        current_decision = existing_states[-1].decision if existing_states else None
        assert_transition_allowed(current=current_decision, requested=decision)

        review_state = ReviewState(
            id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            decision=decision,
            justification=justification,
        )

        if entity_type is ReviewedEntityType.SIGNAL:
            return await self._signal_repository.save_review_state(review_state)
        return await self._briefing_repository.save_review_state(review_state)
