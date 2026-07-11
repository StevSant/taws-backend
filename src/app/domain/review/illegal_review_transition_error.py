from app.domain.review.entities.review_decision import ReviewDecision


class IllegalReviewTransitionError(Exception):
    """Raised when a requested decision isn't reachable from an entity's current decision.

    Lives in `domain/` (not `application/`) — despite the *rule* being enforced at the
    use-case layer (`application/review/review_transition_policy.py`), this exception
    type is also raised by the infrastructure layer: the `review_states_enforce_transition`
    Postgres trigger (`migrations/versions/0002_review_states_transition_trigger.py`) is
    a DB-level backstop against a check-then-insert race between concurrent requests, and
    `SupabaseSignalRepository`/`SupabaseBriefingRepository.save_review_state` translate
    that trigger's rejection into this same error type. Since dependencies point inward
    (`api -> application -> domain <- infrastructure`), a type raised by both
    `application/` and `infrastructure/` must live in `domain/`, the only layer both
    depend on.

    Caught by the API layer (`api/v1/routers/reviews.py`) and translated to
    `409 Conflict` either way — the caller doesn't need to know which layer caught it.
    """

    def __init__(
        self,
        current: ReviewDecision | None,
        requested: ReviewDecision,
        detail: str | None = None,
    ) -> None:
        self.current = current
        self.requested = requested
        if detail is not None:
            message = detail
        elif current is not None:
            message = f"cannot transition from '{current.value}' (terminal) to '{requested.value}'"
        else:
            # `current` is None here specifically for the DB-trigger path: a
            # concurrent request already set a terminal decision after this
            # request's own (now-stale) read, so there's no locally-known `current`
            # to report.
            message = f"cannot apply '{requested.value}': entity is already in a terminal state"
        super().__init__(message)
