from abc import ABC, abstractmethod

from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent


class EventAnalyzerPort(ABC):
    """Port for analyzing a news event and producing an enriched analysis.

    Implementations (e.g. GeminiEventAnalyzer) call an LLM to extract
    structured insights from a raw `NewsEvent`.
    """

    @abstractmethod
    async def analyze(self, event: NewsEvent) -> EnrichedEvent:
        """Analyze a news event and return an enriched version with structured insights."""
        raise NotImplementedError
