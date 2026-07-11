from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SignalEvidence:
    """One piece of evidence (source + date, optionally a historical analog) backing a `Signal`.

    Stored as a JSON array on `signals.evidence` rather than a separate table — see
    `backend/migrations/0001_watchlists_signals_briefings.sql` for the rationale.
    """

    source: str
    published_at: datetime
    url: str | None = None
    detail: str | None = None
