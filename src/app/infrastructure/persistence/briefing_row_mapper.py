from typing import Any

from app.domain.briefing.entities import Briefing, BriefingInstrumentSection
from app.domain.review.entities import OpenReviewItem, ReviewedEntityType
from app.domain.signals.entities import ImpactClass
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def briefing_from_row(row: Any) -> Briefing:
    """Map one `briefings` table row (as returned by `supabase-py`) onto `Briefing`.

    `instrument_breakdown`/`open_review_items` are JSONB columns added in migration 0007
    (issue #16) — PostgREST already decodes them into `list[dict]`, so no extra JSON
    parsing is needed here, same as `evidence` on `signal_row_mapper.py`. Typed `Any`
    rather than `dict[str, Any]` — see `watchlist_row_mapper.py` for why.
    """
    return Briefing(
        id=row["id"],
        watchlist_id=row["watchlist_id"],
        summary=row["summary"],
        disclaimer=row["disclaimer"],
        linked_signal_ids=row.get("linked_signal_ids") or [],
        instrument_breakdown=[
            _instrument_section_from_row(item) for item in row.get("instrument_breakdown") or []
        ],
        open_review_items=[
            _open_review_item_from_row(item) for item in row.get("open_review_items") or []
        ],
        created_at=parse_supabase_timestamp(row["created_at"]),
    )


def briefing_to_instrument_breakdown_column(
    sections: list[BriefingInstrumentSection],
) -> list[dict[str, Any]]:
    """Map `Briefing.instrument_breakdown` onto the JSON-serializable shape stored in
    `briefings.instrument_breakdown`."""
    return [
        {
            "symbol": section.symbol,
            "narrative": section.narrative,
            "impact_classes": [impact_class.value for impact_class in section.impact_classes],
            "signal_ids": section.signal_ids,
            "evidence_sources": section.evidence_sources,
        }
        for section in sections
    ]


def briefing_to_open_review_items_column(items: list[OpenReviewItem]) -> list[dict[str, Any]]:
    """Map `Briefing.open_review_items` onto the JSON-serializable shape stored in
    `briefings.open_review_items`."""
    return [{"entity_type": item.entity_type.value, "entity_id": item.entity_id} for item in items]


def _instrument_section_from_row(item: dict[str, Any]) -> BriefingInstrumentSection:
    return BriefingInstrumentSection(
        symbol=item["symbol"],
        narrative=item["narrative"],
        impact_classes=[ImpactClass(value) for value in item.get("impact_classes") or []],
        signal_ids=item.get("signal_ids") or [],
        evidence_sources=item.get("evidence_sources") or [],
    )


def _open_review_item_from_row(item: dict[str, Any]) -> OpenReviewItem:
    return OpenReviewItem(
        entity_type=ReviewedEntityType(item["entity_type"]), entity_id=item["entity_id"]
    )
