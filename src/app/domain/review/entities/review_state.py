from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.review.entities.review_decision import ReviewDecision
from app.domain.review.entities.reviewed_entity_type import ReviewedEntityType


@dataclass(slots=True)
class ReviewState:
    """One reviewer decision on a signal or briefing — an immutable audit trail entry.

    Each row is who (`user_id`) decided what (`decision`) about which entity
    (`entity_type` + `entity_id`), when (`created_at`), with a required `justification`.
    Rows are append-only: re-reviewing an entity adds a new `ReviewState` rather than
    mutating a prior one, so the audit trail is never lost.
    """

    id: str
    entity_type: ReviewedEntityType
    entity_id: str
    user_id: str
    decision: ReviewDecision
    justification: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
