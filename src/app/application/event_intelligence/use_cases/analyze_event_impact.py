from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.event_intelligence.ports import EventAnalyzerPort


class AnalyzeEventImpact:
    """Use case: analyze how a specific sector or asset is affected by an enriched event.

    Delegates to the `EventAnalyzerPort` (Gemini) for the actual impact analysis.
    The application layer knows nothing about Gemini or any infrastructure detail.
    """

    def __init__(self, analyzer: EventAnalyzerPort) -> None:
        self._analyzer = analyzer

    async def execute(self, event: EnrichedEvent, sector: str) -> str:
        return await self._analyzer.analyze_impact(event, sector)