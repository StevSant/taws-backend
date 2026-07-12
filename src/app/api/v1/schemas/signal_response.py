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
    # Real analytical output (issue #40). `analysis_available` is False when
    # classification fell back to an uncertain/zero-confidence call (no LLM key or an
    # unparseable response); the frontend labels those "análisis no disponible" rather
    # than rendering an empty thesis as if it were real analysis.
    thesis: str = ""
    key_drivers: list[str] = []
    risk_factors: list[str] = []
    analysis_available: bool = True
    price_delta: float | None = None
    created_at: datetime
