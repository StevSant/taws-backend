from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import (
    get_briefing_repository,
    get_signal_repository,
    get_watchlist_repository,
    require_compliance,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser, ReviewDecisionRequest, ReviewStateResponse
from app.application.review import ReviewTargetNotFoundError
from app.application.review.use_cases import SubmitReviewDecision
from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository
from app.domain.review import IllegalReviewTransitionError
from app.domain.review.entities import ReviewedEntityType, ReviewState
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository

router = APIRouter(tags=["reviews"])


async def _get_owned_briefing(
    briefing_id: str,
    user: CurrentUser,
    briefing_repository: BriefingRepository,
    watchlist_repository: WatchlistRepository,
) -> Briefing:
    """Return the briefing if it exists and its watchlist belongs to `user`, else raise 404.

    Briefings are per-user via `watchlist_id` -> `watchlists.user_id`. This backend's
    Supabase client uses the service-role key (bypasses RLS), so the `briefings` RLS
    policy gives zero protection to traffic through this API — ownership must be
    enforced here, mirroring `watchlists.py`'s `_get_owned_watchlist`. 404 (not 403)
    whether the briefing doesn't exist or belongs to another user's watchlist, so this
    endpoint never confirms another user's briefing id exists.
    """
    briefing = await briefing_repository.get(briefing_id)
    if briefing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    watchlist = await watchlist_repository.get(briefing.watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    return briefing


async def _get_briefing_or_404(
    briefing_id: str,
    briefing_repository: BriefingRepository,
) -> Briefing:
    """Return the briefing if it exists, else raise 404 — WITHOUT any ownership check.

    The compliance-review WRITE path uses this (not `_get_owned_briefing`) so a
    compliance reviewer can record a decision on ANY user's briefing, not only their own.
    Access to this path is already gated to `require_compliance`, so dropping the
    owner scope here does not widen exposure to non-compliance callers. Owner-scoped
    reads (generation, GET history, export) keep using `_get_owned_briefing`.
    """
    briefing = await briefing_repository.get(briefing_id)
    if briefing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    return briefing


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
    user: Annotated[CurrentUser, Depends(require_compliance)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
) -> ReviewStateResponse:
    """Record a review decision (reviewed/escalated/discarded) on a signal.

    Restricted to the `compliance` role via `require_compliance` (an anonymous caller is
    rejected with 401 there first, never downgraded to 403). Escalation is only ever a
    `ReviewState` row with `decision="escalated"` — no order, quantity, or execution
    side effect exists anywhere in this path.
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
    user: Annotated[CurrentUser, Depends(require_compliance)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
) -> ReviewStateResponse:
    """Record a review decision (reviewed/escalated/discarded) on a briefing.

    Restricted to the `compliance` role via `require_compliance` (an anonymous caller is
    rejected with 401 there first, never downgraded to 403). A compliance reviewer may
    review ANY user's briefing, so this WRITE path uses `_get_briefing_or_404` (existence
    only) rather than the owner-scoped `_get_owned_briefing` used by the read paths.
    Escalation is only ever a `ReviewState` row with `decision="escalated"` — no order,
    quantity, or execution side effect exists anywhere in this path.
    """
    await _get_briefing_or_404(briefing_id, briefing_repository)
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
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> list[ReviewStateResponse]:
    """List the full review audit trail for a briefing, most recent last.

    The briefing must belong (via its watchlist) to the authenticated user — see
    `_get_owned_briefing`.
    """
    await _get_owned_briefing(briefing_id, user, briefing_repository, watchlist_repository)
    states = await briefing_repository.list_review_states(briefing_id)
    return [ReviewStateResponse.model_validate(state) for state in states]
