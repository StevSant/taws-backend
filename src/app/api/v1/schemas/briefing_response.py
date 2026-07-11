from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BriefingResponse(BaseModel):
    """Response payload for a single Advisor-generated briefing."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    watchlist_id: str
    summary: str
    disclaimer: str
    linked_signal_ids: list[str]
    created_at: datetime
