from typing import Any

from app.domain.review.entities import ReviewDecision, ReviewedEntityType, ReviewState
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def review_state_from_row(row: Any) -> ReviewState:
    """Map one `review_states` table row (as returned by `supabase-py`) onto `ReviewState`.

    Typed `Any` rather than `dict[str, Any]` — see `watchlist_row_mapper.py` for why.
    """
    return ReviewState(
        id=row["id"],
        entity_type=ReviewedEntityType(row["entity_type"]),
        entity_id=row["entity_id"],
        user_id=row["user_id"],
        decision=ReviewDecision(row["decision"]),
        justification=row["justification"],
        created_at=parse_supabase_timestamp(row["created_at"]),
    )


def review_state_to_row(review_state: ReviewState) -> dict[str, Any]:
    """Map a `ReviewState` onto the row shape `review_states` expects on insert.

    Shared by `SupabaseSignalRepository.save_review_state` and
    `SupabaseBriefingRepository.save_review_state` so the two adapters don't
    duplicate this serialization.
    """
    return {
        "id": review_state.id,
        "entity_type": review_state.entity_type.value,
        "entity_id": review_state.entity_id,
        "user_id": review_state.user_id,
        "decision": review_state.decision.value,
        "justification": review_state.justification,
        "created_at": review_state.created_at.isoformat(),
    }
