from enum import StrEnum


class ReviewedEntityType(StrEnum):
    """Which kind of entity a `ReviewState` is attached to."""

    SIGNAL = "signal"
    BRIEFING = "briefing"
