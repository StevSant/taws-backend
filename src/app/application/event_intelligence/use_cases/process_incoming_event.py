from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.domain.event_intelligence.ports import EventAnalyzerPort, EventRepositoryPort


class ProcessIncomingEvent:
    """Use case: receive a raw news event, analyze it, persist the result.

    This is the core pipeline of the Event Intelligence (Sentinel) module.
    It orchestrates the analyzer and repository ports — the application layer
    knows nothing about Gemini, in-memory storage, or any infrastructure detail.
    """

    def __init__(
        self,
        analyzer: EventAnalyzerPort,
        repository: EventRepositoryPort,
    ) -> None:
        self._analyzer = analyzer
        self._repository = repository

    async def execute(self, event: NewsEvent) -> EnrichedEvent:
        enriched = await self._analyzer.analyze(event)
        await self._repository.save(enriched)
        return enriched
