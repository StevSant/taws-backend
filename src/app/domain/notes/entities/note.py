from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class Note:
    """A short, free-text note authored and owned by a single user (issue #62).

    Not tied to a specific briefing or scenario: notes are per-user scratch notes surfaced
    by the shared Guía/Notas panel on both the Briefings and Scenario Lab pages, so the same
    notes follow the user across both.
    """

    id: str
    user_id: str
    body: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
