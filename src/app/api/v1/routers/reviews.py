from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import (
    get_briefing_repository,
    get_signal_repository,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser, ReviewDecisionRequest, ReviewStateResponse
from app.application.review import ReviewTargetNotFoundError
from app.application.review.use_cases import SubmitReviewDecision
from app.domain.briefing.ports import BriefingRepository
from app.domain.review import IllegalReviewTransitionError
from app.domain.review.entities import ReviewedEntityType, ReviewState
from app.domain.signals.ports import SignalRepository

router = APIRouter(tags=["reviews"])


async def _submit_review(
    use_case: SubmitReviewDecision,
    entity_type: ReviewedEntityType,
    entity_id: str,
    user: CurrentUser,
    payload: ReviewDecisionRequest,
) -> ReviewState:
    """Run `SubmitReviewDecision`, translating its domain errors to HTTP responses.

    `404` when the entity doesn't exist, `409` when the requested decision isn't a
    legal transition from the entity's current decision — whether caught by the
    fast app-layer check (`application/review/review_transition_policy.py`) or by
    the DB-level backstop trigger for a concurrent-request race (migration `0002`);
    both surface as the same `IllegalReviewTransitionError`. `user_id` always comes
    from the authenticated `user`, never from the request body.
    """
    try:
        return await use_case.execute(
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user.id,
            decision=payload.decision,
            justification=payload.justification,
        )
    except ReviewTargetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IllegalReviewTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/signals/{signal_id}/reviews", status_code=status.HTTP_201_CREATED)
async def submit_signal_review(
    signal_id: str,
    payload: ReviewDecisionRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
) -> ReviewStateResponse:
    """Record a review decision (reviewed/escalated/discarded) on a signal.

    Escalation is only ever a `ReviewState` row with `decision="escalated"` — no
    order, quantity, or execution side effect exists anywhere in this path.
    """
    use_case = SubmitReviewDecision(
        signal_repository=signal_repository, briefing_repository=briefing_repository
    )
    review_state = await _submit_review(
        use_case, ReviewedEntityType.SIGNAL, signal_id, user, payload
    )
    return ReviewStateResponse.model_validate(review_state)


@router.get("/signals/{signal_id}/reviews")
async def list_signal_reviews(
    signal_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
) -> list[ReviewStateResponse]:
    """List the full review audit trail for a signal, most recent last."""
    signal = await signal_repository.get(signal_id)
    if signal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    states = await signal_repository.list_review_states(signal_id)
    return [ReviewStateResponse.model_validate(state) for state in states]


@router.post("/briefings/{briefing_id}/reviews", status_code=status.HTTP_201_CREATED)
async def submit_briefing_review(
    briefing_id: str,
    payload: ReviewDecisionRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
) -> ReviewStateResponse:
    """Record a review decision (reviewed/escalated/discarded) on a briefing.

    Escalation is only ever a `ReviewState` row with `decision="escalated"` — no
    order, quantity, or execution side effect exists anywhere in this path.
    """
    use_case = SubmitReviewDecision(
        signal_repository=signal_repository, briefing_repository=briefing_repository
    )
    review_state = await _submit_review(
        use_case, ReviewedEntityType.BRIEFING, briefing_id, user, payload
    )
    return ReviewStateResponse.model_validate(review_state)


@router.get("/briefings/{briefing_id}/reviews")
async def list_briefing_reviews(
    briefing_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
) -> list[ReviewStateResponse]:
    """List the full review audit trail for a briefing, most recent last."""
    briefing = await briefing_repository.get(briefing_id)
    if briefing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    states = await briefing_repository.list_review_states(briefing_id)
    return [ReviewStateResponse.model_validate(state) for state in states]
