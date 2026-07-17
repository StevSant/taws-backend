from enum import StrEnum


class NoteTargetKind(StrEnum):
    """What kind of object a note is about.

    These values are written to `user_notes.target_kind` and are pinned by that column's
    check constraint (migration 0024) — changing one is a schema change, not a rename.
    """

    BRIEFING = "briefing"
    SCENARIO = "scenario"
    INSTRUMENT = "instrument"
