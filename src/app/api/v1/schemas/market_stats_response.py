from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.candle_response import CandleResponse
from app.api.v1.schemas.unusual_move_response import UnusualMoveResponse
from app.application.quant.volatility_regime import VolatilityRegime


class MarketStatsResponse(BaseModel):
    """Response payload for `GET /api/v1/quant/stats`.

    `candles` is the OHLC series behind the derived metrics (oldest -> newest, `[]`
    when no series is available), so a client can draw a candlestick chart from the
    same response — see `api/v1/mappers/map_price_candle_to_candle_response.py`.
    """

    model_config = ConfigDict(from_attributes=True)

    instrument_symbol: str
    window_days: int
    last_price: float | None
    price_delta_pct: float | None
    volatility_pct: float | None
    volatility_regime: VolatilityRegime | None
    unusual_moves: list[UnusualMoveResponse]
    candles: list[CandleResponse]
    as_of: datetime
