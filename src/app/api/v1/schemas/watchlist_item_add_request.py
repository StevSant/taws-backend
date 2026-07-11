from pydantic import BaseModel, Field


class WatchlistItemAddRequest(BaseModel):
    """Request payload for `POST /api/v1/watchlists/{watchlist_id}/items`."""

    symbol: str = Field(..., min_length=1, max_length=20)
