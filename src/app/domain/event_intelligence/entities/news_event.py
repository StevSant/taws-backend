from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewsEvent:
    """A raw news event ingested from a provider (Yahoo, Marketaux, demo, ...).

    This is the input to the Event Intelligence pipeline. The `EventAnalyzerPort`
    will enrich it into an `EnrichedEvent`.
    """

    title: str
    description: str
    content: str
    source: str
    url: str | None = None
    published_at: datetime | None = None
