from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EarningsCalendarEntryResponse(BaseModel):
    """Response payload for one instrument's next earnings date + "upcoming earnings risk" flag."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    earnings_date: datetime
    is_upcoming_risk: bool
