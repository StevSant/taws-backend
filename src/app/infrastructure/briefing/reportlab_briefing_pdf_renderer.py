from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, PropertySet, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.domain.briefing.entities import Briefing, BriefingInstrumentSection
from app.domain.briefing.ports import BriefingDocumentRenderer
from app.domain.review.entities import OpenReviewItem

_PAGE_MARGIN = 0.75 * inch
_BULLET_CHAR = "•"


class ReportLabBriefingPdfRenderer(BriefingDocumentRenderer):
    """PDF adapter for `BriefingDocumentRenderer`, built on `reportlab`.

    Chosen over `weasyprint` for this sandbox (issue #22): `weasyprint` renders
    HTML/CSS through Cairo/Pango, which are system-level shared libraries `pip`/`uv`
    cannot install — `weasyprint`'s Python package installs fine, but fails at
    *import* time here with `OSError: cannot load library 'libgobject-2.0-0'`.
    `reportlab` is pure-Python (plus `pillow`, a normal wheel), so it has no such
    runtime dependency and works identically in any environment, including CI.

    Lays out the exact document structure issue #16 added to `Briefing`: a
    title/date header, the executive summary, one section per
    `BriefingInstrumentSection` in `instrument_breakdown`, the `open_review_items`
    list, and the `disclaimer` footer — see `BriefingDocumentRenderer`'s docstring
    for why every one of those must be present in the rendered output.
    """

    def render(self, briefing: Briefing) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=_PAGE_MARGIN,
            rightMargin=_PAGE_MARGIN,
            topMargin=_PAGE_MARGIN,
            bottomMargin=_PAGE_MARGIN,
            title=f"TAWS Briefing {briefing.id}",
        )
        styles = _build_styles()

        story: list = []
        story.extend(_build_header(briefing, styles))
        story.extend(_build_executive_summary(briefing, styles))
        story.extend(_build_instrument_breakdown(briefing.instrument_breakdown, styles))
        story.extend(_build_open_review_items(briefing.open_review_items, styles))
        story.extend(_build_disclaimer(briefing, styles))

        document.build(story)
        return buffer.getvalue()


def _build_styles() -> dict[str, PropertySet]:
    base = getSampleStyleSheet()
    return {
        "title": base["Title"],
        "meta": ParagraphStyle("Meta", parent=base["Normal"], textColor=colors.grey, spaceAfter=12),
        "heading": base["Heading2"],
        "subheading": base["Heading3"],
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], alignment=TA_LEFT, spaceAfter=8, leading=14
        ),
        "list_item": ParagraphStyle(
            "ListItem",
            parent=base["Normal"],
            alignment=TA_LEFT,
            leading=13,
            leftIndent=18,
            bulletIndent=6,
            spaceAfter=2,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.grey,
            spaceBefore=16,
        ),
    }


def _build_header(briefing: Briefing, styles: dict[str, PropertySet]) -> list:
    # Literal Unicode punctuation ("·", not the `&middot;` XML entity name) so
    # this never interacts with `_escape`'s `&` -> `&amp;` replacement below — mixing
    # a hand-written XML entity into a string that also gets escaped double-escapes
    # the entity into literal, unrendered text (see `_build_open_review_items`'s fix
    # for the bug this exact mistake caused there).
    created_at = briefing.created_at.strftime("%Y-%m-%d %H:%M UTC")
    meta_text = _escape(
        f"Watchlist {briefing.watchlist_id} · generated {created_at} · briefing id {briefing.id}"
    )
    return [
        Paragraph("TAWS Briefing", styles["title"]),
        Paragraph(meta_text, styles["meta"]),
        HRFlowable(width="100%", color=colors.lightgrey, spaceAfter=12),
    ]


def _build_executive_summary(briefing: Briefing, styles: dict[str, PropertySet]) -> list:
    return [
        Paragraph("Executive summary", styles["heading"]),
        Paragraph(_escape(briefing.summary), styles["body"]),
        Spacer(1, 8),
    ]


def _build_instrument_breakdown(
    sections: list[BriefingInstrumentSection], styles: dict[str, PropertySet]
) -> list:
    if not sections:
        return []
    story: list = [Paragraph("Instrument breakdown", styles["heading"])]
    for section in sections:
        story.extend(_build_instrument_section(section, styles))
    story.append(Spacer(1, 4))
    return story


def _build_instrument_section(
    section: BriefingInstrumentSection, styles: dict[str, PropertySet]
) -> list:
    story: list = [
        Paragraph(section.symbol, styles["subheading"]),
        Paragraph(_escape(section.narrative), styles["body"]),
    ]
    if section.impact_classes:
        impact_summary = ", ".join(impact.value for impact in section.impact_classes)
        story.append(Paragraph(f"<b>Impact classes:</b> {impact_summary}", styles["list_item"]))
    if section.evidence_sources:
        story.append(Paragraph("<b>Evidence sources:</b>", styles["list_item"]))
        story.extend(_bullet_list(section.evidence_sources, styles["list_item"]))
    story.append(Spacer(1, 8))
    return story


def _build_open_review_items(items: list[OpenReviewItem], styles: dict[str, PropertySet]) -> list:
    story: list = [Paragraph("Open review items", styles["heading"])]
    if not items:
        story.append(Paragraph("No open review items.", styles["body"]))
        return story
    # Literal "—" (not the `&mdash;` XML entity name) — same reasoning as
    # `_build_header`'s comment: `_bullet_list` escapes every line via `_escape`, which
    # would otherwise turn a hand-written entity's `&` into `&amp;`, corrupting it into
    # literal, unrendered `&mdash;` text instead of an em dash.
    labels = [f"{item.entity_type.value.capitalize()} — {item.entity_id}" for item in items]
    story.extend(_bullet_list(labels, styles["list_item"]))
    story.append(Spacer(1, 8))
    return story


def _build_disclaimer(briefing: Briefing, styles: dict[str, PropertySet]) -> list:
    return [
        HRFlowable(width="100%", color=colors.lightgrey, spaceBefore=12, spaceAfter=8),
        Paragraph(_escape(briefing.disclaimer), styles["disclaimer"]),
    ]


def _bullet_list(lines: list[str], style: PropertySet) -> list[Paragraph]:
    """Render `lines` as a simple bulleted list.

    Plain `Paragraph(..., bulletText=...)` flowables rather than `ListFlowable`/
    `ListItem` — visually equivalent for this document's flat, one-level lists, and
    avoids `ListItem` not satisfying `ListFlowable`'s declared flowable type.
    """
    return [Paragraph(_escape(line), style, bulletText=_BULLET_CHAR) for line in lines]


def _escape(text: str) -> str:
    """Escape XML-significant characters before handing `text` to reportlab's
    `Paragraph`, which parses its input as a small XML-like markup language — raw
    briefing content (LLM-composed or fallback) must never be interpreted as markup.
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    )
