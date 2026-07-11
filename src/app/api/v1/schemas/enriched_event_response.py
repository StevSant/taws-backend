from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.news_event_response import NewsEventResponse


class EnrichedEventResponse(BaseModel):
    """Response payload for an analyzed (enriched) event from the Sentinel pipeline."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original: NewsEventResponse
    summary: str
    importance: float
    should_notify: bool
    affected_assets: list[str]
    affected_sectors: list[str]
    confidence: float
    reasoning: str
    suggested_questions: list[str]
    analyzed_at: datetime
