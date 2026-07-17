"""Unit tests for the PDF renderer's signal labels and hyperlinks.

"Open review items" used to render raw UUIDs. With the enriched
`RenderableBriefing`, resolved signal items must render as human-readable labels
(`Signal — MSFT · Negative · 80% confidence`) wrapped in a working hyperlink to the
frontend's `/radar/{symbol}` page, and each instrument-breakdown section header must
link its symbol the same way. Unresolved signals and briefing-type items keep the
raw-id label. Labels stay escaped (the file documents prior double-escaping bugs),
so a markup-bearing symbol must render literally, never as markup.
"""

from datetime import UTC, datetime
from io import BytesIO

from pypdf import PdfReader

from app.domain.briefing.entities import (
    Briefing,
    BriefingInstrumentSection,
    RenderableBriefing,
    RenderableSignalRef,
)
from app.domain.review.entities import OpenReviewItem, ReviewedEntityType
from app.domain.signals.entities import ImpactClass
from app.infrastructure.briefing import ReportLabBriefingPdfRenderer

_BASE = "https://app.example.com"


def _briefing(symbol: str = "MSFT") -> Briefing:
    return Briefing(
        id="brief-1",
        watchlist_id="wl-1",
        summary="Executive summary.",
        disclaimer="This is not personalized financial advice.",
        instrument_breakdown=[
            BriefingInstrumentSection(
                symbol=symbol, narrative="Narrative.", signal_ids=["sig-full"]
            ),
        ],
        open_review_items=[
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="sig-full"),
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="sig-partial"),
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="sig-gone"),
            OpenReviewItem(entity_type=ReviewedEntityType.BRIEFING, entity_id="brief-0"),
        ],
        created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )


def _renderable(symbol: str = "MSFT") -> RenderableBriefing:
    return RenderableBriefing(
        briefing=_briefing(symbol),
        signal_refs={
            "sig-full": RenderableSignalRef(
                signal_id="sig-full",
                symbol=symbol,
                link_url=f"{_BASE}/radar/{symbol}",
                impact_class=ImpactClass.NEGATIVE,
                confidence=0.8,
            ),
            "sig-partial": RenderableSignalRef(
                signal_id="sig-partial",
                symbol="NVDA",
                link_url=f"{_BASE}/radar/NVDA",
            ),
        },
        instrument_links={symbol: f"{_BASE}/radar/{symbol}"},
    )


def _render(renderable: RenderableBriefing) -> tuple[str, list[str]]:
    """Render and return `(extracted_text, link_annotation_uris)`."""
    pdf_bytes = ReportLabBriefingPdfRenderer().render(renderable)
    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() for page in reader.pages)
    uris: list[str] = []
    for page in reader.pages:
        for annotation in page.get("/Annots") or []:
            action = annotation.get_object().get("/A")
            if action is not None and action.get("/URI") is not None:
                uris.append(str(action["/URI"]))
    return text, uris


def test_resolved_signal_review_item_renders_enriched_label_with_link() -> None:
    text, uris = _render(_renderable())

    assert "Signal — MSFT · Negative · 80% confidence" in text
    assert f"{_BASE}/radar/MSFT" in uris


def test_breakdown_fallback_signal_renders_symbol_only_label_with_link() -> None:
    text, uris = _render(_renderable())

    assert "Signal — NVDA" in text
    # No impact/confidence suffix for a breakdown-only fallback.
    assert "Signal — NVDA ·" not in text
    assert f"{_BASE}/radar/NVDA" in uris


def test_unresolved_signal_and_briefing_items_keep_raw_id_labels() -> None:
    text, uris = _render(_renderable())

    assert "Signal — sig-gone" in text
    assert "Briefing — brief-0" in text
    assert not any("sig-gone" in uri or "brief-0" in uri for uri in uris)


def test_instrument_section_header_symbol_is_hyperlinked() -> None:
    _text, uris = _render(_renderable())

    # Once for the section header, once for the resolved review item.
    assert uris.count(f"{_BASE}/radar/MSFT") == 2


def test_markup_bearing_symbol_in_link_label_renders_literally() -> None:
    symbol = "MSFT</b>"
    text, uris = _render(_renderable(symbol=symbol))

    assert "MSFT</b>" in text
    assert any("/radar/MSFT" in uri for uri in uris)
