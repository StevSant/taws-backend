from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WatchlistResponse(BaseModel):
    """Response payload for a single watchlist."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    created_at: datetime
    position: int | None = None
