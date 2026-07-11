from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class Watchlist:
    """A named, user-owned collection of tracked instruments."""

    id: str
    user_id: str
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
