from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UnusualMoveResponse(BaseModel):
    """Response payload for a single unusual-move day within `MarketStatsResponse`."""

    model_config = ConfigDict(from_attributes=True)

    date: datetime
    return_pct: float
    z_score: float
