from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.sentiment.entities import FearGreedClassification


class FearGreedReadingResponse(BaseModel):
    """Response payload for the current market-wide Fear & Greed Index reading."""

    model_config = ConfigDict(from_attributes=True)

    value: int
    classification: FearGreedClassification
    as_of: datetime
