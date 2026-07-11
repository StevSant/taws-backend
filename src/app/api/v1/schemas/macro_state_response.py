from pydantic import BaseModel

from app.api.v1.schemas.macro_observation_response import MacroObservationResponse
from app.api.v1.schemas.volatility_regime_response import VolatilityRegimeResponse


class MacroStateResponse(BaseModel):
    """Response payload for `GET /api/v1/macro`: combined rates + CPI + volatility regime."""

    rates: MacroObservationResponse
    cpi: MacroObservationResponse
    volatility: VolatilityRegimeResponse
