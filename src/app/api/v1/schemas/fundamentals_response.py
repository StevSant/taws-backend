from pydantic import BaseModel

from app.api.v1.schemas.earnings_calendar_entry_response import EarningsCalendarEntryResponse
from app.api.v1.schemas.instrument_fundamentals_response import InstrumentFundamentalsResponse


class FundamentalsResponse(BaseModel):
    """Response payload for `GET /api/v1/fundamentals/{symbol}`: fundamentals + earnings
    calendar."""

    fundamentals: InstrumentFundamentalsResponse
    earnings: EarningsCalendarEntryResponse | None = None
