from enum import StrEnum


class ReviewDecision(StrEnum):
    """Outcome a human reviewer records against a signal or briefing.

    Alert/task-shaped only — no trading/execution decisions exist here (no buy/sell/
    order/quantity), per the product's compliance stance (see
    `docs/specs/2026-07-11-track5-product-focus.md`, HU3).
    """

    REVIEWED = "reviewed"
    ESCALATED = "escalated"
    DISCARDED = "discarded"
