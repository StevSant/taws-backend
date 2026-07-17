from dataclasses import dataclass, field

from app.domain.briefing.entities.briefing import Briefing
from app.domain.briefing.entities.renderable_signal_ref import RenderableSignalRef


@dataclass(frozen=True, slots=True)
class RenderableBriefing:
    """A `Briefing` plus the read-time enrichment the document renderer needs.

    The `BriefingDocumentRenderer` port stays a pure sync `document -> bytes`
    adapter, so everything that requires I/O — resolving referenced signal ids,
    composing absolute frontend links from the configured base URL — happens
    upstream in `ExportBriefingDocument` and travels here as plain data. Lives in
    the domain (not `application/`) because the renderer port's signature refers to
    it, and domain ports may only depend inward.

    - `signal_refs`: per referenced signal id, the resolved symbol/impact/
      confidence/link (`RenderableSignalRef`). Ids that could not be resolved at
      all have no entry — the renderer falls back to its raw-id label.
    - `instrument_links`: per `instrument_breakdown` symbol, the absolute
      `/radar/{symbol}` URL for the section header.
    """

    briefing: Briefing
    signal_refs: dict[str, RenderableSignalRef] = field(default_factory=dict)
    instrument_links: dict[str, str] = field(default_factory=dict)
