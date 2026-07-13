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

    @abstractmethod
    async def get(self, event_id: str) -> EnrichedEvent | None:
        """Return the enriched event with this id, or `None` if it isn't stored.

        Needed by the inline-button callbacks on a broadcast news alert: Telegram caps
        `callback_data` at 64 bytes, so a tapped button can only send back an id — the event
        itself has to be looked up again here.

        `None` is an expected, routine outcome, not an error: enriched events currently live in
        an in-memory store, so any restart drops them while the alert message (and its buttons)
        stays in the user's Telegram history forever. Callers must handle the miss gracefully
        rather than treat it as a failure.
        """
        raise NotImplementedError
