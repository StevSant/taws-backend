from dataclasses import dataclass
from datetime import datetime

from app.domain.event_intelligence.entities.news_event import NewsEvent


@dataclass(slots=True)
class EnrichedEvent:
    """A news event that has been analyzed by the Event Intelligence pipeline.

    Carries the Gemini-produced analysis alongside the original `NewsEvent`.
    """

    id: str
    original: NewsEvent
    summary: str
    importance: float
    should_notify: bool
    affected_assets: list[str]
    affected_sectors: list[str]
    confidence: float
    reasoning: str
    suggested_questions: list[str]
    analyzed_at: datetime
