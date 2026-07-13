from pydantic import BaseModel, ConfigDict


class RefreshAnalysisResponse(BaseModel):
    """Response payload for `POST /api/v1/analysis/refresh` (issue #29): a summary of one
    shared-analysis refresh pass.

    `refreshed` counts `(symbol, locale)` pairs the pass handled successfully — including pairs
    whose analysis was ALREADY fresh and therefore cost nothing, since the freshness gate lives
    inside the generate use cases and is invisible from the caller's side. A high `refreshed`
    number is not a bill; a non-zero `failed` is the thing worth looking at.
    """

    model_config = ConfigDict(from_attributes=True)

    symbols: int
    locales: int
    refreshed: int
    failed: int
