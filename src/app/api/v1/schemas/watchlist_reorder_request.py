from pydantic import BaseModel, Field


class WatchlistReorderRequest(BaseModel):
    """Request payload for `PATCH /api/v1/watchlists/reorder` (issue #66).

    `ordered_ids` is the full desired order of the caller's watchlists, front to back.
    Ids not owned by the caller are silently ignored (see `WatchlistRepository.reorder`).
    """

    ordered_ids: list[str] = Field(..., min_length=1)
