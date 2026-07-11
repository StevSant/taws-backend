from dataclasses import dataclass, field

from app.domain.signals.entities import ImpactClass


@dataclass(slots=True)
class BriefingInstrumentSection:
    """One per-instrument mini-section inside a fuller `Briefing` document (issue #16).

    `narrative` is a short, LLM-composed line grounded strictly in `signal_ids`'
    underlying `Signal`s (see `GenerateBriefing._compose_briefing`) — or a deterministic,
    data-derived fallback string when structured composition isn't available (no API key,
    a malformed response) or when this instrument has no signals at all, exactly mirroring
    `GenerateSignal`'s "never invent facts, degrade to a plain data-derived string instead"
    precedent (`application/signals/use_cases/generate_signal.py`).

    `impact_classes`/`signal_ids`/`evidence_sources` are built deterministically (no LLM
    involved) by grouping the same signals already fetched for the executive-summary
    composition — one source of truth, no second fetch.
    """

    symbol: str
    narrative: str
    impact_classes: list[ImpactClass] = field(default_factory=list)
    signal_ids: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
