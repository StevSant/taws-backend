from typing import Any

from app.domain.notes.entities import Note
from app.domain.notes.value_objects import NoteTarget, NoteTargetKind
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp

# Which FK column holds the live id, per kind. The exclusive-arc pattern: exactly one of
# these is populated for a live target, and all of them are null once it is deleted.
_ID_COLUMN_BY_KIND = {
    NoteTargetKind.BRIEFING: "briefing_id",
    NoteTargetKind.SCENARIO: "scenario_id",
    NoteTargetKind.INSTRUMENT: "instrument_symbol",
}


def _target_from_row(row: Any) -> NoteTarget | None:
    """Build the note's target, or None when the note was never linked.

    `target_kind` — not the FK — decides whether a target exists at all. A row with a kind
    but a null FK is a note whose target was deleted: still a target, no longer available.

    `row` is `Any`, not `dict[str, Any]`: `supabase-py` types `response.data` as `JSON`
    (a recursive union including `float`), which pyright will not narrow to a dict at the
    call site. Every row mapper in this package takes `Any` for that reason.
    """
    raw_kind = row.get("target_kind")
    if raw_kind is None:
        return None

    kind = NoteTargetKind(raw_kind)
    return NoteTarget(
        kind=kind,
        label=row.get("target_label") or "",
        target_id=row.get(_ID_COLUMN_BY_KIND[kind]),
        watchlist_id=row.get("target_watchlist_id"),
    )


def note_from_row(row: Any) -> Note:
    """Map one `user_notes` table row (as returned by `supabase-py`) onto `Note`."""
    return Note(
        id=row["id"],
        user_id=row["user_id"],
        body=row["body"],
        target=_target_from_row(row),
        created_at=parse_supabase_timestamp(row["created_at"]),
        updated_at=parse_supabase_timestamp(row["updated_at"]),
    )


def note_target_columns(target: NoteTarget | None) -> dict[str, Any]:
    """Map a target to the six `user_notes` columns it occupies.

    Always returns all six keys so an insert writes an explicit null into every arc it is
    not using — which is what the `user_notes_target_kind_matches` check constraint asserts.
    """
    if target is None:
        return {
            "target_kind": None,
            "briefing_id": None,
            "scenario_id": None,
            "instrument_symbol": None,
            "target_watchlist_id": None,
            "target_label": None,
        }

    columns: dict[str, Any] = {
        "target_kind": target.kind.value,
        "briefing_id": None,
        "scenario_id": None,
        "instrument_symbol": None,
        "target_watchlist_id": target.watchlist_id,
        "target_label": target.label,
    }
    columns[_ID_COLUMN_BY_KIND[target.kind]] = target.target_id
    return columns
