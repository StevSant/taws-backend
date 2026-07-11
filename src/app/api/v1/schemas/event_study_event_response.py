from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventStudyEventResponse(BaseModel):
    """Response payload for a single matched event within `EventStudyResponse`."""

    model_config = ConfigDict(from_attributes=True)

    date: datetime
    return_pct: float
