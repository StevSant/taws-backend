"""Notes domain (issue #62): per-user free-text notes — entities, value objects, ports."""

from app.domain.notes.entities.note import Note
from app.domain.notes.value_objects import NoteTarget, NoteTargetKind

__all__ = ["Note", "NoteTarget", "NoteTargetKind"]
