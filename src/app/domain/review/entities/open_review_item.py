from dataclasses import dataclass

from app.domain.review.entities.reviewed_entity_type import ReviewedEntityType


@dataclass(frozen=True, slots=True)
class OpenReviewItem:
    """A signal or briefing that has no recorded reviewer decision yet — "pending action".

    Surfaced on the fuller `Briefing` document (issue #16) via `GenerateBriefing.
    _gather_open_review_items`: an entity with an empty `list_review_states(...)` result
    IS an open item, so this is a read-time projection over the existing `ReviewState`
    audit trail (issue #4), not a new persisted "reviewed" flag. Lives in `domain/review/`
    (not `domain/briefing/`) since it's a review-domain concept — `entity_type` +
    `entity_id` shaped just like `ReviewState` itself — that any future consumer beyond
    `Briefing` could reuse.
    """

    entity_type: ReviewedEntityType
    entity_id: str
