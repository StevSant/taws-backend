from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.event_intelligence.ports import EventRepositoryPort


class MemoryEventRepository(EventRepositoryPort):
    """In-memory implementation of `EventRepositoryPort`.

    Stores enriched events in a plain list. Suitable for development,
    demo, and testing — not for production (no persistence across restarts).
    """

    def __init__(self) -> None:
        self._events: list[EnrichedEvent] = []

    async def save(self, event: EnrichedEvent) -> None:
        self._events.append(event)

    async def list_all(self) -> list[EnrichedEvent]:
        return list(self._events)

    async def get(self, event_id: str) -> EnrichedEvent | None:
        return next((event for event in self._events if event.id == event_id), None)
