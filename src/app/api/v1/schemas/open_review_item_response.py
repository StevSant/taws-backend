from pydantic import BaseModel, ConfigDict

from app.domain.review.entities import ReviewedEntityType


class OpenReviewItemResponse(BaseModel):
    """Response payload for one signal/briefing still pending a reviewer decision."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: ReviewedEntityType
    entity_id: str
