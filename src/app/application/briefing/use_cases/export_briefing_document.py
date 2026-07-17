from urllib.parse import quote

from app.domain.briefing.entities import (
    Briefing,
    RenderableBriefing,
    RenderableSignalRef,
    find_symbol_for_signal_id,
)
from app.domain.briefing.ports import BriefingDocumentRenderer
from app.domain.notification.ports import EmailSender
from app.domain.review.entities import ReviewedEntityType
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository

_EMAIL_SUBJECT_TEMPLATE = "TAWS Briefing — watchlist {watchlist_id}"
_ATTACHMENT_FILENAME_TEMPLATE = "briefing-{briefing_id}.pdf"
_RADAR_LINK_TEMPLATE = "{base_url}/radar/{symbol}"


class ExportBriefingDocument:
    """Briefing export pipeline (issue #22): a persisted `Briefing` -> a PDF, either
    returned directly for download (`render_pdf`) or attached to an email
    (`send_by_email`). Both paths enrich and render through the same
    `_build_renderable` + `BriefingDocumentRenderer` pipeline, so the PDF a user
    downloads and the PDF a user gets emailed are always byte-for-byte the same
    document.

    Enrichment happens here (not in the renderer, which stays a pure sync
    `document -> bytes` adapter): every signal id the briefing references — the
    union of `linked_signal_ids` and signal-type `open_review_items` — is resolved
    in ONE `get_by_ids` batch call, falling back to the briefing's own
    `instrument_breakdown` for ids retention has pruned, and each recovered symbol
    gets a precomputed absolute `/radar/{symbol}` link built from the configured
    frontend base URL (same pattern as `run_watchdog_scan`'s alert links).

    `send_by_email` depends on `EmailSender`, which currently has exactly one
    adapter — `LoggingEmailSender`, a no-op/logging stand-in (see that adapter's
    docstring for why a real SMTP/email-service integration is deferred). Calling
    `send_by_email` today logs the composed email instead of delivering it; this use
    case doesn't know or care which adapter is behind the port, same as every other
    port-based use case in this codebase.
    """

    def __init__(
        self,
        document_renderer: BriefingDocumentRenderer,
        email_sender: EmailSender,
        signal_repository: SignalRepository,
        frontend_base_url: str,
    ) -> None:
        self._document_renderer = document_renderer
        self._email_sender = email_sender
        self._signal_repository = signal_repository
        self._frontend_base_url = frontend_base_url.rstrip("/")

    async def render_pdf(self, briefing: Briefing) -> bytes:
        """Render `briefing` to PDF bytes, ready to stream back as a download."""
        return self._document_renderer.render(await self._build_renderable(briefing))

    async def send_by_email(self, briefing: Briefing, recipient: str) -> None:
        """Render `briefing` to PDF and hand it to the configured `EmailSender` as an
        attachment for `recipient`."""
        pdf_bytes = self._document_renderer.render(await self._build_renderable(briefing))
        await self._email_sender.send(
            to=recipient,
            subject=_EMAIL_SUBJECT_TEMPLATE.format(watchlist_id=briefing.watchlist_id),
            body=briefing.summary,
            attachment=pdf_bytes,
            attachment_filename=_ATTACHMENT_FILENAME_TEMPLATE.format(briefing_id=briefing.id),
        )

    async def _build_renderable(self, briefing: Briefing) -> RenderableBriefing:
        """Resolve every referenced signal id (one batch call) into a `RenderableBriefing`."""
        signal_ids = _referenced_signal_ids(briefing)
        signals = await self._signal_repository.get_by_ids(signal_ids)
        return RenderableBriefing(
            briefing=briefing,
            signal_refs=_build_signal_refs(briefing, signal_ids, signals, self._frontend_base_url),
            instrument_links=_build_instrument_links(briefing, self._frontend_base_url),
        )


def _referenced_signal_ids(briefing: Briefing) -> list[str]:
    """Union of `linked_signal_ids` and signal-type `open_review_items`, order-preserving."""
    seen: dict[str, None] = dict.fromkeys(briefing.linked_signal_ids)
    for item in briefing.open_review_items:
        if item.entity_type is ReviewedEntityType.SIGNAL:
            seen.setdefault(item.entity_id, None)
    return list(seen)


def _build_signal_refs(
    briefing: Briefing,
    signal_ids: list[str],
    signals: dict[str, Signal],
    frontend_base_url: str,
) -> dict[str, RenderableSignalRef]:
    """One `RenderableSignalRef` per id whose symbol could be recovered.

    Repository hit -> full ref (symbol/impact/confidence); repository miss with a
    breakdown-section match -> partial ref (symbol only); neither -> no ref, so the
    renderer keeps its raw-id label for that item.
    """
    refs: dict[str, RenderableSignalRef] = {}
    for signal_id in signal_ids:
        ref = _build_signal_ref(signal_id, briefing, signals, frontend_base_url)
        if ref is not None:
            refs[signal_id] = ref
    return refs


def _build_signal_ref(
    signal_id: str,
    briefing: Briefing,
    signals: dict[str, Signal],
    frontend_base_url: str,
) -> RenderableSignalRef | None:
    signal = signals.get(signal_id)
    if signal is not None:
        return RenderableSignalRef(
            signal_id=signal_id,
            symbol=signal.instrument_symbol,
            link_url=_radar_link(frontend_base_url, signal.instrument_symbol),
            impact_class=signal.impact_class,
            confidence=signal.confidence,
        )
    symbol = find_symbol_for_signal_id(briefing.instrument_breakdown, signal_id)
    if symbol is None:
        return None
    return RenderableSignalRef(
        signal_id=signal_id, symbol=symbol, link_url=_radar_link(frontend_base_url, symbol)
    )


def _build_instrument_links(briefing: Briefing, frontend_base_url: str) -> dict[str, str]:
    """Absolute `/radar/{symbol}` link per breakdown section, for the section headers."""
    return {
        section.symbol: _radar_link(frontend_base_url, section.symbol)
        for section in briefing.instrument_breakdown
    }


def _radar_link(frontend_base_url: str, symbol: str) -> str:
    """Same `{base}/radar/{symbol}` pattern as `run_watchdog_scan`'s alert links.

    Symbols are length-validated only (a pair like `BTC/USD` is possible), so the
    path segment is percent-encoded to keep the URL structurally valid.
    """
    return _RADAR_LINK_TEMPLATE.format(base_url=frontend_base_url, symbol=quote(symbol, safe=""))
