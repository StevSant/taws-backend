from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.fear_greed_reading_response import FearGreedReadingResponse
from app.api.v1.schemas.signal_evidence_response import SignalEvidenceResponse
from app.domain.sentiment.entities import SentimentLabel


class SentimentReadingResponse(BaseModel):
    """Response payload for a Sentiment Analyst-generated reading (issue #21)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    instrument_symbol: str
    tone_score: float
    tone_label: SentimentLabel
    fear_greed: FearGreedReadingResponse
    evidence: list[SignalEvidenceResponse]
    rationale: str
    disclaimer: str
    created_at: datetime
