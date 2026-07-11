from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class Briefing:
    """An Advisor-agent-produced summary for one watchlist, grounded in linked signals.

    Written by the Advisor agent (issue #3), on-demand or on a scheduled daily run.
    `disclaimer` is a product invariant (never personalized advice), persisted here.
    """

    id: str
    watchlist_id: str
    summary: str
    disclaimer: str
    linked_signal_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
