from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.review.entities import ReviewDecision, ReviewedEntityType


class ReviewStateResponse(BaseModel):
    """Response payload for a single `ReviewState` (one audit trail entry)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: ReviewedEntityType
    entity_id: str
    user_id: str
    decision: ReviewDecision
    justification: str
    created_at: datetime
