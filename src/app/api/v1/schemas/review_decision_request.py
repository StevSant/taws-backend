from pydantic import BaseModel, Field, field_validator

from app.domain.review.entities import ReviewDecision


class ReviewDecisionRequest(BaseModel):
    """Request payload for `POST /api/v1/{signals|briefings}/{entity_id}/reviews`.

    `justification` mirrors the DB's `check (char_length(justification) > 0)` on
    `review_states` at the schema layer, so an empty justification surfaces a clean
    `422` instead of relying on the DB constraint to reject the insert. `min_length=1`
    alone would still accept a whitespace-only string (e.g. `"   "`), so the field is
    also stripped and re-checked for emptiness.
    """

    decision: ReviewDecision
    justification: str = Field(..., min_length=1)

    @field_validator("justification")
    @classmethod
    def _reject_blank_justification(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("justification must not be blank")
        return stripped
