from app.domain.review.entities import ReviewedEntityType


class ReviewTargetNotFoundError(Exception):
    """Raised when a review decision targets a signal/briefing that doesn't exist.

    Caught by the API layer (`api/v1/routers/reviews.py`) and translated to
    `404 Not Found` — the entity must exist before any review state can be recorded
    against it.
    """

    def __init__(self, entity_type: ReviewedEntityType, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type.value} '{entity_id}' not found")
