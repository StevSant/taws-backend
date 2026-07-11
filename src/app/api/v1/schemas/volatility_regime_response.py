from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.market.entities import VolatilityLevel


class VolatilityRegimeResponse(BaseModel):
    """Response payload for the current VIX-derived volatility regime."""

    model_config = ConfigDict(from_attributes=True)

    vix_level: float
    regime: VolatilityLevel
    as_of: datetime
