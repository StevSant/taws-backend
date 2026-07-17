from dataclasses import dataclass

from app.domain.notes.value_objects.note_target_kind import NoteTargetKind


@dataclass(frozen=True, slots=True)
class NoteTarget:
    """The object a note is about, as recorded when the note was written.

    `kind` and `label` are durable — they survive the target's deletion, so a note can
    still say what it was about after the thing it was about is gone. `target_id` is the
    liveness bit: the database nulls it via `on delete set null`, which is exactly what
    `available` reports.

    `label` is a snapshot and is deliberately NOT refreshed if the target is later
    renamed — it records what the object was called when the note's author saw it.

    `watchlist_id` is set for briefings only: `/briefings` renders only the active
    watchlist's reports, so a deep link has to pre-select the right one.
    """

    kind: NoteTargetKind
    label: str
    target_id: str | None = None
    watchlist_id: str | None = None

    @property
    def available(self) -> bool:
        """Whether the target still exists. False once the database nulled the FK."""
        return self.target_id is not None
