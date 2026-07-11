from app.domain.review.entities import ReviewDecision


class IllegalReviewTransitionError(Exception):
    """Raised when a requested decision isn't reachable from an entity's current decision.

    Caught by the API layer (`api/v1/routers/reviews.py`) and translated to
    `409 Conflict`. See `review_transition_policy.assert_transition_allowed` for the
    state machine rule this enforces.
    """

    def __init__(self, current: ReviewDecision, requested: ReviewDecision) -> None:
        self.current = current
        self.requested = requested
        super().__init__(
            f"cannot transition from '{current.value}' (terminal) to '{requested.value}'"
        )
