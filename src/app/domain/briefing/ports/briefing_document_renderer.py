from abc import ABC, abstractmethod

from app.domain.briefing.entities import Briefing


class BriefingDocumentRenderer(ABC):
    """Port for rendering a full `Briefing` document into downloadable file bytes.

    Backs the briefing export feature (issue #22): `GET
    /api/v1/briefings/{id}/export.pdf` and the "trigger an email send" endpoint both
    render through this same port. Issue #22 ships exactly one adapter —
    `ReportLabBriefingPdfRenderer` (`infrastructure/briefing/
    reportlab_briefing_pdf_renderer.py`), producing a PDF. `render` returns raw bytes
    rather than a PDF-specific type so a future adapter (a different PDF engine, or a
    different format entirely) can implement this same port without touching
    `application/`/`api/` — same "swap the adapter, not the port" rule as every other
    port in this codebase.

    Every section of issue #16's fuller `Briefing` document must be rendered legibly:
    a title/date header, the executive summary (`Briefing.summary`), one section per
    `BriefingInstrumentSection` in `instrument_breakdown`, the `open_review_items`
    list, and the `disclaimer` footer. The rendered document must never drop the
    disclaimer — the same "never personalized advice" product invariant the source
    `Briefing` already carries must survive into the exported document.
    """

    @abstractmethod
    def render(self, briefing: Briefing) -> bytes:
        """Render `briefing` into raw document bytes (e.g. a PDF).

        Synchronous by design: laying out an already-fetched, already-persisted
        `Briefing` is pure CPU work, no network/DB I/O — unlike the ports in
        `domain/notification`, which do need to be async because delivery is I/O.
        """
        raise NotImplementedError
