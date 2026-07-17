"""Unit tests for `ExportBriefingDocument`'s signal enrichment (PDF export).

The renderer is a pure sync `document -> bytes` adapter, so all I/O-bound
enrichment happens here in the use case: one `get_by_ids` batch over the union of
`linked_signal_ids` and signal-type `open_review_items`, producing a
`RenderableBriefing` that carries, per resolvable signal id, the symbol, impact,
confidence, and a precomputed absolute `/radar/{symbol}` link.

Contracts pinned here:
- ONE batch lookup covering the union of referenced signal ids (briefing-type
  review items excluded);
- repository hit -> full ref (symbol + impact + confidence + link);
- repository miss with a breakdown section match -> partial ref (symbol + link only);
- id in neither place -> no ref at all (renderer keeps the raw-id label);
- every breakdown symbol gets an absolute `/radar/{symbol}` link (base URL taken
  from settings, trailing slash tolerated);
- `render_pdf` and `send_by_email` hand the renderer the SAME enriched document,
  preserving the byte-for-byte download/email guarantee.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from app.application.briefing.use_cases import ExportBriefingDocument
from app.domain.briefing.entities import (
    Briefing,
    BriefingInstrumentSection,
    RenderableBriefing,
)
from app.domain.briefing.ports import BriefingDocumentRenderer
from app.domain.notification.ports import EmailSender
from app.domain.review.entities import OpenReviewItem, ReviewedEntityType, ReviewState
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.signals.ports import SignalRepository

_FRONTEND_BASE_URL = "https://app.example.com/"
_PDF_BYTES = b"%PDF-fake"


class _RecordingRenderer(BriefingDocumentRenderer):
    def __init__(self) -> None:
        self.rendered: list[RenderableBriefing] = []

    def render(self, briefing: RenderableBriefing) -> bytes:
        self.rendered.append(briefing)
        return _PDF_BYTES


class _RecordingEmailSender(EmailSender):
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachment: bytes | None = None,
        attachment_filename: str | None = None,
    ) -> None:
        self.sent.append(
            {
                "to": to,
                "subject": subject,
                "body": body,
                "attachment": attachment,
                "attachment_filename": attachment_filename,
            }
        )


class _FakeSignalRepository(SignalRepository):
    def __init__(self, known: dict[str, Signal]) -> None:
        self._known = known
        self.batch_calls: list[list[str]] = []

    async def create(self, signal: Signal) -> Signal:
        raise NotImplementedError

    async def get(self, signal_id: str) -> Signal | None:
        raise AssertionError("ExportBriefingDocument must use get_by_ids, not per-id get()")

    async def get_by_ids(self, signal_ids: Sequence[str]) -> dict[str, Signal]:
        self.batch_calls.append(list(signal_ids))
        return {
            signal_id: self._known[signal_id]
            for signal_id in signal_ids
            if signal_id in self._known
        }

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        raise NotImplementedError

    async def get_latest_for_instrument(self, symbol: str, locale: str) -> Signal | None:
        raise NotImplementedError

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        raise NotImplementedError

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        raise NotImplementedError


def _known_signal() -> Signal:
    return Signal(
        id="sig-known",
        instrument_symbol="AAPL",
        impact_class=ImpactClass.NEGATIVE,
        confidence=0.8,
        evidence=[],
        disclaimer="not personalized advice",
    )


def _briefing() -> Briefing:
    return Briefing(
        id="brief-1",
        watchlist_id="wl-1",
        summary="summary",
        disclaimer="not personalized advice",
        linked_signal_ids=["sig-known"],
        instrument_breakdown=[
            BriefingInstrumentSection(symbol="MSFT", narrative="n", signal_ids=["sig-pruned"]),
        ],
        open_review_items=[
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="sig-known"),
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="sig-pruned"),
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="sig-gone"),
            OpenReviewItem(entity_type=ReviewedEntityType.BRIEFING, entity_id="brief-0"),
        ],
        created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )


def _build_use_case() -> tuple[ExportBriefingDocument, _RecordingRenderer, _FakeSignalRepository]:
    renderer = _RecordingRenderer()
    repository = _FakeSignalRepository({"sig-known": _known_signal()})
    use_case = ExportBriefingDocument(
        document_renderer=renderer,
        email_sender=_RecordingEmailSender(),
        signal_repository=repository,
        frontend_base_url=_FRONTEND_BASE_URL,
    )
    return use_case, renderer, repository


async def test_render_pdf_enriches_with_one_batch_lookup_over_the_id_union() -> None:
    use_case, renderer, repository = _build_use_case()

    pdf_bytes = await use_case.render_pdf(_briefing())

    assert pdf_bytes == _PDF_BYTES
    # One batch call over the union: linked ids + signal-type review items, deduped,
    # briefing-type review items excluded.
    assert repository.batch_calls == [["sig-known", "sig-pruned", "sig-gone"]]

    renderable = renderer.rendered[0]
    assert renderable.briefing == _briefing()

    known = renderable.signal_refs["sig-known"]
    assert known.symbol == "AAPL"
    assert known.impact_class == ImpactClass.NEGATIVE
    assert known.confidence == 0.8
    assert known.link_url == "https://app.example.com/radar/AAPL"

    # Pruned signal: symbol recovered from the breakdown section, no impact/confidence.
    pruned = renderable.signal_refs["sig-pruned"]
    assert pruned.symbol == "MSFT"
    assert pruned.impact_class is None
    assert pruned.confidence is None
    assert pruned.link_url == "https://app.example.com/radar/MSFT"

    # In neither the repository nor the breakdown: no ref, renderer keeps the raw id.
    assert "sig-gone" not in renderable.signal_refs

    # Every breakdown symbol gets a section-header link; trailing slash stripped.
    assert renderable.instrument_links == {"MSFT": "https://app.example.com/radar/MSFT"}


async def test_symbols_are_percent_encoded_in_radar_links() -> None:
    pair_signal = Signal(
        id="sig-pair",
        instrument_symbol="BTC/USD",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.6,
        evidence=[],
        disclaimer="not personalized advice",
    )
    renderer = _RecordingRenderer()
    use_case = ExportBriefingDocument(
        document_renderer=renderer,
        email_sender=_RecordingEmailSender(),
        signal_repository=_FakeSignalRepository({"sig-pair": pair_signal}),
        frontend_base_url=_FRONTEND_BASE_URL,
    )
    briefing = Briefing(
        id="brief-2",
        watchlist_id="wl-1",
        summary="summary",
        disclaimer="not personalized advice",
        linked_signal_ids=["sig-pair"],
        instrument_breakdown=[
            BriefingInstrumentSection(symbol="BTC/USD", narrative="n", signal_ids=["sig-pair"]),
        ],
        created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    await use_case.render_pdf(briefing)

    renderable = renderer.rendered[0]
    # A slash in the symbol must not create an extra path segment.
    assert renderable.signal_refs["sig-pair"].link_url == "https://app.example.com/radar/BTC%2FUSD"
    assert renderable.instrument_links == {"BTC/USD": "https://app.example.com/radar/BTC%2FUSD"}


async def test_send_by_email_attaches_the_same_enriched_document() -> None:
    renderer = _RecordingRenderer()
    email_sender = _RecordingEmailSender()
    use_case = ExportBriefingDocument(
        document_renderer=renderer,
        email_sender=email_sender,
        signal_repository=_FakeSignalRepository({"sig-known": _known_signal()}),
        frontend_base_url=_FRONTEND_BASE_URL,
    )
    briefing = _briefing()

    downloaded = await use_case.render_pdf(briefing)
    await use_case.send_by_email(briefing, recipient="dev@example.com")

    # Both paths render the SAME enriched document — byte-for-byte guarantee holds.
    assert renderer.rendered[0] == renderer.rendered[1]
    sent = email_sender.sent[0]
    assert sent["attachment"] == downloaded
    assert sent["to"] == "dev@example.com"
    assert sent["subject"] == "TAWS Briefing — watchlist wl-1"
    assert sent["body"] == briefing.summary
    assert sent["attachment_filename"] == "briefing-brief-1.pdf"
