from pydantic import BaseModel, Field

from app.domain.review.entities import ReviewDecision


class ReviewDecisionRequest(BaseModel):
    """Request payload for `POST /api/v1/{signals|briefings}/{entity_id}/reviews`.

    `justification` mirrors the DB's `check (char_length(justification) > 0)` on
    `review_states` at the schema layer, so an empty justification surfaces a clean
    `422` instead of relying on the DB constraint to reject the insert.
    """

    decision: ReviewDecision
    justification: str = Field(..., min_length=1)
