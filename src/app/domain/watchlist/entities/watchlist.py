from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class Watchlist:
    """A named, user-owned collection of tracked instruments."""

    id: str
    user_id: str
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    position: int | None = None
    """User-defined display order (issue #66). `None` = never reordered; the list API
    sorts those after positioned lists, by `created_at`."""
