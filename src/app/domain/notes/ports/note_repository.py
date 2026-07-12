from abc import ABC, abstractmethod

from app.domain.notes.entities import Note


class NoteRepository(ABC):
    """Port for persisting a user's notes (issue #62), scoped to the owning user."""

    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[Note]:
        """Return every note owned by `user_id`, most-recently-updated first."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, note_id: str) -> Note | None:
        """Return the note with this id, or `None` if it doesn't exist."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, note: Note) -> Note:
        """Create a new note and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, note_id: str, body: str) -> Note:
        """Update an existing note's body and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, note_id: str) -> None:
        """Delete a note."""
        raise NotImplementedError
