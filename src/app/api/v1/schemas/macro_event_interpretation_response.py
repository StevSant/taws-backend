from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.macro_asset_class_impact_response import MacroAssetClassImpactResponse
from app.api.v1.schemas.macro_observation_response import MacroObservationResponse
from app.api.v1.schemas.volatility_regime_response import VolatilityRegimeResponse


class MacroEventInterpretationResponse(BaseModel):
    """Response payload for a Macro Analyst-generated interpretation (issue #21)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_description: str
    rates: MacroObservationResponse
    cpi: MacroObservationResponse
    volatility_regime: VolatilityRegimeResponse
    asset_class_impacts: list[MacroAssetClassImpactResponse]
    disclaimer: str
    created_at: datetime
