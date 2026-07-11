"""Review domain: reviewer decisions (reviewed/escalated/discarded) on signals and briefings.

Shared by `domain/signals/` and `domain/briefing/` — a `ReviewState` always references
either a `Signal` or a `Briefing` by id, never a trading/execution record. Persistence is
exposed as a primitive on `SignalRepository`/`BriefingRepository` (`save_review_state`).
`IllegalReviewTransitionError` lives here (not `application/`) because it's raised by
both the use-case layer (`application/review/review_transition_policy.py`) and the
infrastructure layer (the `review_states_enforce_transition` DB trigger's rejection,
translated by the Supabase adapters) — see that error's docstring for why.
"""

from app.domain.review.illegal_review_transition_error import IllegalReviewTransitionError

__all__ = ["IllegalReviewTransitionError"]
