from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.signal_evidence_response import SignalEvidenceResponse
from app.domain.signals.entities import ImpactClass


class SignalResponse(BaseModel):
    """Response payload for a single Analyst-generated signal."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    instrument_symbol: str
    impact_class: ImpactClass
    confidence: float
    evidence: list[SignalEvidenceResponse]
    disclaimer: str
    price_delta: float | None = None
    created_at: datetime
