from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.signals.entities.impact_class import ImpactClass
from app.domain.signals.entities.signal_evidence import SignalEvidence


@dataclass(slots=True)
class Signal:
    """An Analyst-agent-produced impact call for one instrument.

    Written by the Analyst agent (issue #2). `disclaimer` is a product invariant
    (never personalized advice) enforced by the Risk & Compliance agent upstream —
    persisted here, not computed at read time. No trading/execution fields exist.
    """

    id: str
    instrument_symbol: str
    impact_class: ImpactClass
    confidence: float
    evidence: list[SignalEvidence]
    disclaimer: str
    price_delta: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
