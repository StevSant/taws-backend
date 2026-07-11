from supabase import PostgrestAPIError

from app.domain.review import IllegalReviewTransitionError
from app.domain.review.entities import ReviewDecision

_TRIGGER_ERROR_CODE = "P0001"
_TRIGGER_MESSAGE_PREFIX = "illegal_review_transition"


def build_illegal_review_transition_error(
    exc: PostgrestAPIError, requested: ReviewDecision
) -> IllegalReviewTransitionError | None:
    """Translate the `review_states_enforce_transition` DB trigger's rejection.

    That trigger (`migrations/versions/0002_review_states_transition_trigger.py`) is
    the atomic backstop against a check-then-insert race in
    `SubmitReviewDecision.execute()`: it re-derives the entity's latest decision at
    insert time (inside a `pg_advisory_xact_lock`) and raises a plain Postgres
    exception with `errcode = 'P0001'` when that latest decision is terminal.
    PostgREST forwards it as a `PostgrestAPIError` with `.code == "P0001"` and
    `.message` set to the trigger's `RAISE EXCEPTION` text (prefixed
    `illegal_review_transition: ` by convention). Imported from the top-level
    `supabase` package (which re-exports it), not the transitive `postgrest`
    package directly — `postgrest` isn't a direct `pyproject.toml` dependency.

    Returns the translated `IllegalReviewTransitionError` (with `current=None`,
    since the adapter has no independent knowledge of the entity's true current
    decision — the whole point of this trigger is that the caller's own read of it
    was stale) if `exc` is this trigger's rejection, else `None` — callers re-raise
    the original `exc` unchanged in that case, since it's some other, unrelated
    Postgrest/Postgres failure.
    """
    if exc.code == _TRIGGER_ERROR_CODE and (exc.message or "").startswith(_TRIGGER_MESSAGE_PREFIX):
        return IllegalReviewTransitionError(current=None, requested=requested, detail=exc.message)
    return None
