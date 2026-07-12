from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.sentiment.entities import FearGreedClassification


class MarketIndexQuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    label: str
    price: float
    change_pct: float


class MarketPulseResponse(BaseModel):
    """Stock-market sentiment snapshot for the Radar macro panel."""

    model_config = ConfigDict(from_attributes=True)

    value: int
    classification: FearGreedClassification
    as_of: datetime
    delta_points: float
    market: str
    source: str
    indices: list[MarketIndexQuoteResponse]
