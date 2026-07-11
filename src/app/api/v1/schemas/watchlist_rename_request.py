from pydantic import BaseModel, Field


class WatchlistRenameRequest(BaseModel):
    """Request payload for `PATCH /api/v1/watchlists/{watchlist_id}`."""

    name: str = Field(..., min_length=1, max_length=200)
