from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.unusual_move_response import UnusualMoveResponse
from app.application.quant.volatility_regime import VolatilityRegime


class MarketStatsResponse(BaseModel):
    """Response payload for `GET /api/v1/quant/stats`."""

    model_config = ConfigDict(from_attributes=True)

    instrument_symbol: str
    window_days: int
    last_price: float | None
    price_delta_pct: float | None
    volatility_pct: float | None
    volatility_regime: VolatilityRegime | None
    unusual_moves: list[UnusualMoveResponse]
    as_of: datetime
