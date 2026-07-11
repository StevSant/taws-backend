from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    """Request payload for `POST /api/v1/watchlists`."""

    name: str = Field(..., min_length=1, max_length=200)
