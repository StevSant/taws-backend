from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    """Response payload for a single Watchdog-composed alert."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    signal_id: str
    watchlist_id: str
    instrument_symbol: str
    consequence_hint: str
    link_url: str
    created_at: datetime
