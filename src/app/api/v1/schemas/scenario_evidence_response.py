from pydantic import BaseModel, ConfigDict

from app.domain.scenario.entities import EvidenceType


class ScenarioEvidenceResponse(BaseModel):
    """Response payload for one grounding-policy-tagged evidence item."""

    model_config = ConfigDict(from_attributes=True)

    evidence_type: EvidenceType
    detail: str
