import asyncio
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.notes.entities import Note
from app.domain.notes.ports import NoteRepository


class InMemoryNoteRepository(NoteRepository):
    """Process-local note storage for development without Supabase credentials."""

    def __init__(self) -> None:
        self._notes: dict[str, Note] = {}
        self._lock = asyncio.Lock()

    async def list_for_user(self, user_id: str) -> list[Note]:
        async with self._lock:
            notes = [replace(note) for note in self._notes.values() if note.user_id == user_id]
        return sorted(notes, key=lambda note: note.updated_at, reverse=True)

    async def get(self, note_id: str) -> Note | None:
        async with self._lock:
            note = self._notes.get(note_id)
            return replace(note) if note is not None else None

    async def create(self, note: Note) -> Note:
        persisted = replace(note)
        async with self._lock:
            self._notes[note.id] = persisted
        return replace(persisted)

    async def update(self, note_id: str, body: str) -> Note:
        async with self._lock:
            current = self._notes[note_id]
            updated = replace(current, body=body, updated_at=datetime.now(UTC))
            self._notes[note_id] = updated
        return replace(updated)

    async def delete(self, note_id: str) -> None:
        async with self._lock:
            self._notes.pop(note_id, None)
