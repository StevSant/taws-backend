from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.scenario_evidence_response import ScenarioEvidenceResponse
from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


class ScenarioAssetClassImpactResponse(BaseModel):
    """Response payload for one entry in a `ScenarioResult.impact_map`."""

    model_config = ConfigDict(from_attributes=True)

    asset_class: AssetClass
    direction: ImpactClass
    confidence: float
    evidence: list[ScenarioEvidenceResponse]
