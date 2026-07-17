from abc import ABC, abstractmethod

from app.domain.notes.value_objects import NoteTarget, NoteTargetKind


class NoteTargetResolver(ABC):
    """Port resolving `(kind, id)` to the live target it names.

    Resolving server-side buys two things: creating a note validates that its target
    actually exists, and the label cannot be spoofed or drift — the client never sends
    display text.
    """

    @abstractmethod
    async def resolve(self, kind: NoteTargetKind, target_id: str) -> NoteTarget | None:
        """Return the live target, or `None` if no such object exists."""
        raise NotImplementedError
