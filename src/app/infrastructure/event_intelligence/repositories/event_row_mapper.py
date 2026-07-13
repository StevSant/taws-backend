from typing import Any

from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def enriched_event_from_row(row: Any) -> EnrichedEvent:
    """Map one `events` table row (as returned by `supabase-py`) onto `EnrichedEvent`.

    The row flattens the entity: the wrapped `NewsEvent`'s fields carry an `original_`
    prefix, the Gemini analysis fields don't. `affected_assets` / `affected_sectors` /
    `suggested_questions` are Postgres `text[]`, which PostgREST hands back as JSON arrays,
    so they need re-listing but no parsing.

    `original_published_at` is the one nullable timestamp here — a provider may not date an
    article — so it is guarded, while `analyzed_at` (always stamped by our own pipeline)
    is not.

    Typed `Any` rather than `dict[str, Any]`: `postgrest`'s response rows are typed as the
    broad `JSON` union, which pyright won't narrow to `dict` automatically — same rationale
    as `note_row_mapper.py`.
    """
    published_at = row["original_published_at"]
    return EnrichedEvent(
        id=row["id"],
        original=NewsEvent(
            title=row["original_title"],
            description=row["original_description"],
            content=row["original_content"],
            source=row["original_source"],
            url=row["original_url"],
            published_at=parse_supabase_timestamp(published_at) if published_at else None,
        ),
        summary=row["summary"],
        importance=float(row["importance"]),
        should_notify=bool(row["should_notify"]),
        affected_assets=list(row["affected_assets"]),
        affected_sectors=list(row["affected_sectors"]),
        confidence=float(row["confidence"]),
        reasoning=row["reasoning"],
        suggested_questions=list(row["suggested_questions"]),
        analyzed_at=parse_supabase_timestamp(row["analyzed_at"]),
    )
