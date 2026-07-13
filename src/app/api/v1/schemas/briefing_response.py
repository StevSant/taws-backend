from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.briefing_instrument_section_response import (
    BriefingInstrumentSectionResponse,
)
from app.api.v1.schemas.linked_signal_response import LinkedSignalResponse
from app.api.v1.schemas.open_review_item_response import OpenReviewItemResponse


class BriefingResponse(BaseModel):
    """Response payload for a single Advisor-generated briefing.

    `summary` doubles as the document's executive summary; `instrument_breakdown` and
    `open_review_items` are the fuller document structure issue #16 adds — see
    `domain/briefing/entities/briefing.py` for the full shape rationale.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    watchlist_id: str
    summary: str
    disclaimer: str
    linked_signal_ids: list[str]
    # Human-readable view of `linked_signal_ids`, resolved from the `Signal` store in the
    # briefings router. `linked_signal_ids` (raw UUIDs) is kept for backward compatibility;
    # `linked_signals` is additive. Defaults to `[]` so `model_validate(briefing)` still
    # works — the domain `Briefing` entity carries only the ids, and the router fills this.
    linked_signals: list[LinkedSignalResponse] = []
    instrument_breakdown: list[BriefingInstrumentSectionResponse]
    open_review_items: list[OpenReviewItemResponse]
    created_at: datetime
