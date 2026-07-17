from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.notes.value_objects import NoteTarget


@dataclass(slots=True)
class Note:
    """A short, free-text note authored and owned by a single user (issue #62).

    A note may optionally be *about* something — a briefing, a scenario, or an
    instrument — via `target`. An unlinked note (`target is None`) is a plain notepad
    entry. A linked note survives its target's deletion: `target.available` goes False
    while `target.label` still says what it was about.
    """

    id: str
    user_id: str
    body: str
    target: NoteTarget | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
