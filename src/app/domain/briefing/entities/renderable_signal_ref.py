from dataclasses import dataclass

from app.domain.signals.entities import ImpactClass


@dataclass(frozen=True, slots=True)
class RenderableSignalRef:
    """Read-time, renderer-facing projection of one signal a briefing references.

    Built by `ExportBriefingDocument` (never persisted): the export pipeline
    resolves each referenced signal id — from the repository when the signal still
    exists, else from the briefing's own `instrument_breakdown` (retention prunes
    signal rows, so ids dangle) — into the symbol, classification, and a
    precomputed absolute frontend link the document renderer needs. A ref exists
    only when a symbol could be recovered at all; `impact_class`/`confidence` are
    `None` for a breakdown-only fallback, where the pruned signal's numbers are
    gone for good.
    """

    signal_id: str
    symbol: str
    link_url: str
    impact_class: ImpactClass | None = None
    confidence: float | None = None
