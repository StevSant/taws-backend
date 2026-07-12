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

    `thesis`/`key_drivers`/`risk_factors` are the real analytical output (issue #40): a
    3-5 sentence thesis, the factors driving the call, and what would invalidate it.
    `analysis_available` is `False` when classification fell back (no LLM key / an
    unparseable response) to an uncertain/zero-confidence call — the frontend uses it to
    label "análisis no disponible" instead of presenting an empty thesis as real analysis.
    """

    id: str
    instrument_symbol: str
    impact_class: ImpactClass
    confidence: float
    evidence: list[SignalEvidence]
    disclaimer: str
    thesis: str = ""
    key_drivers: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    analysis_available: bool = True
    price_delta: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
