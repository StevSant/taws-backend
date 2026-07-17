from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, PropertySet, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.domain.briefing.entities import (
    Briefing,
    BriefingInstrumentSection,
    RenderableBriefing,
    RenderableSignalRef,
)
from app.domain.briefing.ports import BriefingDocumentRenderer
from app.domain.review.entities import OpenReviewItem, ReviewedEntityType

_PAGE_MARGIN = 0.75 * inch
_BULLET_CHAR = "•"
# Style constant (like the `colors.grey`/`colors.lightgrey` literals below), not
# config: link affordance blue, underlined, so anchors read as links in the PDF.
_LINK_COLOR = "#1d4ed8"


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

    def render(self, briefing: RenderableBriefing) -> bytes:
        source = briefing.briefing
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=_PAGE_MARGIN,
            rightMargin=_PAGE_MARGIN,
            topMargin=_PAGE_MARGIN,
            bottomMargin=_PAGE_MARGIN,
            title=f"TAWS Briefing {source.id}",
        )
        styles = _build_styles()

        story: list = []
        story.extend(_build_header(source, styles))
        story.extend(_build_executive_summary(source, styles))
        story.extend(
            _build_instrument_breakdown(
                source.instrument_breakdown, briefing.instrument_links, styles
            )
        )
        story.extend(
            _build_open_review_items(source.open_review_items, briefing.signal_refs, styles)
        )
        story.extend(_build_disclaimer(source, styles))

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
    sections: list[BriefingInstrumentSection],
    instrument_links: dict[str, str],
    styles: dict[str, PropertySet],
) -> list:
    if not sections:
        return []
    story: list = [Paragraph("Instrument breakdown", styles["heading"])]
    for section in sections:
        story.extend(_build_instrument_section(section, instrument_links, styles))
    story.append(Spacer(1, 4))
    return story


def _build_instrument_section(
    section: BriefingInstrumentSection,
    instrument_links: dict[str, str],
    styles: dict[str, PropertySet],
) -> list:
    # `symbol` comes from `WatchlistItemAddRequest.symbol` (length-validated only, no
    # charset restriction, just `.upper()`'d) via `GenerateBriefing`, so it's exactly as
    # untrusted as `narrative`/`evidence_sources` below — it was missed here once (an
    # unescaped `</b>` in a symbol threw an unhandled reportlab paraparser `ValueError`,
    # a 500 on every future export until the item was removed), so it must stay wrapped
    # in `_escape()` like every other entity-derived field in this file. `_hyperlink`
    # receives the ALREADY-escaped symbol and must never be re-escaped afterwards.
    heading_markup = _escape(section.symbol)
    link_url = instrument_links.get(section.symbol)
    if link_url is not None:
        heading_markup = _hyperlink(heading_markup, link_url)
    story: list = [
        Paragraph(heading_markup, styles["subheading"]),
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


def _build_open_review_items(
    items: list[OpenReviewItem],
    signal_refs: dict[str, RenderableSignalRef],
    styles: dict[str, PropertySet],
) -> list:
    story: list = [Paragraph("Open review items", styles["heading"])]
    if not items:
        story.append(Paragraph("No open review items.", styles["body"]))
        return story
    # Each line is built as ALREADY-escaped markup (`_open_review_item_markup`
    # escapes label text and URL individually before assembling the anchor), so it
    # must NOT go through `_bullet_list`/`_escape` again — re-escaping assembled
    # markup is exactly the double-escaping bug documented in `_build_header`.
    story.extend(
        Paragraph(
            _open_review_item_markup(item, signal_refs),
            styles["list_item"],
            bulletText=_BULLET_CHAR,
        )
        for item in items
    )
    story.append(Spacer(1, 8))
    return story


def _open_review_item_markup(
    item: OpenReviewItem, signal_refs: dict[str, RenderableSignalRef]
) -> str:
    """Markup for one open review item: an enriched hyperlink when the signal
    resolved (fully or via the breakdown fallback), else the raw-id label.

    Literal "—"/"·" (not `&mdash;`/`&middot;` XML entity names) — same reasoning as
    `_build_header`'s comment: the label goes through `_escape`, which would turn a
    hand-written entity's `&` into `&amp;`, corrupting it into literal text.
    """
    ref = signal_refs.get(item.entity_id) if item.entity_type is ReviewedEntityType.SIGNAL else None
    if ref is None:
        return _escape(f"{item.entity_type.value.capitalize()} — {item.entity_id}")
    label = f"Signal — {ref.symbol}"
    if ref.impact_class is not None and ref.confidence is not None:
        # Breakdown-only fallbacks carry no impact/confidence — symbol-only label.
        label = f"{label} · {ref.impact_class.value.capitalize()} · {ref.confidence:.0%} confidence"
    return _hyperlink(_escape(label), ref.link_url)


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


def _hyperlink(escaped_label: str, url: str) -> str:
    """Wrap ALREADY-escaped label markup in a reportlab anchor, colored/underlined
    so it reads as a link.

    CRITICAL: `escaped_label` must have gone through `_escape` already, and the
    returned markup must never be passed through `_escape` again — escaping
    assembled markup turns the anchor's own `<`/`&` into literal text (the same
    double-escaping failure mode documented at `_build_header`). The URL is escaped
    here (plus `"` for the attribute position) because it embeds entity-derived
    symbols, which are exactly as untrusted as any other briefing field.
    """
    href = _escape(url).replace('"', "&quot;")
    return f'<a href="{href}"><font color="{_LINK_COLOR}"><u>{escaped_label}</u></font></a>'


def _escape(text: str) -> str:
    """Escape XML-significant characters before handing `text` to reportlab's
    `Paragraph`, which parses its input as a small XML-like markup language — raw
    briefing content (LLM-composed or fallback) must never be interpreted as markup.
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    )
