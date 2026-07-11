from pydantic import BaseModel, ConfigDict

from app.domain.macro.entities import ImpactMagnitude
from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


class MacroAssetClassImpactResponse(BaseModel):
    """Response payload for one entry in a `MacroEventInterpretation.asset_class_impacts`."""

    model_config = ConfigDict(from_attributes=True)

    asset_class: AssetClass
    direction: ImpactClass
    magnitude: ImpactMagnitude
    rationale: str
