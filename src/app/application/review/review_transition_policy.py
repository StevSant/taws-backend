from app.application.review.illegal_review_transition_error import (
    IllegalReviewTransitionError,
)
from app.domain.review.entities import ReviewDecision

_TERMINAL_DECISIONS = frozenset({ReviewDecision.REVIEWED, ReviewDecision.DISCARDED})


def assert_transition_allowed(current: ReviewDecision | None, requested: ReviewDecision) -> None:
    """Enforce the review state machine; raises `IllegalReviewTransitionError` on violation.

    This is the one place the review workflow's transition rule is defined — future
    work (e.g. issue #6's review panel UI) should treat this docstring as the
    authoritative contract, not infer it from behavior.

    Rule:
    - No prior decision (`current is None`): any first decision is allowed — this is
      the entity's first-ever review.
    - `REVIEWED` and `DISCARDED` are TERMINAL: once an entity's latest decision is one
      of these, no further transition is allowed, from either terminal state. They
      represent "this item is done, closed" — a hard stop on the audit trail.
    - `ESCALATED` is NOT terminal: an entity whose latest decision is `ESCALATED` may
      still transition to `REVIEWED`, `DISCARDED`, or `ESCALATED` again (re-escalating,
      e.g. to attach a follow-up justification while it's still open). It represents
      "this needs more attention", which is expected to eventually resolve into one of
      the terminal states.
    - A justification is required on every transition regardless of which decision is
      requested — enforced at the API schema layer (`ReviewDecisionRequest`), not here.

    `current` is the `decision` of the most recent `ReviewState` for the entity (by
    `created_at`), or `None` if it has never been reviewed. Every legal transition
    still inserts a brand-new `ReviewState` row — this workflow never mutates a prior
    row, only decides whether a new one may be added.
    """
    if current is None:
        return
    if current in _TERMINAL_DECISIONS:
        raise IllegalReviewTransitionError(current=current, requested=requested)
