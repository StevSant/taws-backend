from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WatchlistItemResponse(BaseModel):
    """Response payload for a single watchlist item."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    watchlist_id: str
    symbol: str
    added_at: datetime
