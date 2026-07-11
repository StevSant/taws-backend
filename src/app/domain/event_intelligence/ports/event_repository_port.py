from abc import ABC, abstractmethod

from app.domain.event_intelligence.entities import EnrichedEvent


class EventRepositoryPort(ABC):
    """Port for persisting and retrieving enriched events.

    Implementations (MemoryEventRepository, later SupabaseEventRepository, ...)
    store the output of the Event Intelligence pipeline.
    """

    @abstractmethod
    async def save(self, event: EnrichedEvent) -> None:
        """Persist an enriched event."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[EnrichedEvent]:
        """Return all stored enriched events."""
        raise NotImplementedError
