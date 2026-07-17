from app.api.v1.schemas.linked_signal_response import LinkedSignalResponse
from app.domain.briefing.entities import BriefingInstrumentSection, find_symbol_for_signal_id
from app.domain.signals.entities import ImpactClass


def linked_signal_from_breakdown(
    signal_id: str, instrument_breakdown: list[BriefingInstrumentSection]
) -> LinkedSignalResponse | None:
    """Build a partially-resolved `LinkedSignalResponse` from the briefing's own breakdown.

    Retention prunes signal rows while briefings keep referencing their ids, so a
    repository miss doesn't have to mean "unknown instrument": when a breakdown
    section still lists the id, the section's `symbol` is recovered — the frontend
    can render a real `/radar/{symbol}` link instead of "Signal unavailable" — with
    neutral impact/confidence, since the pruned signal's numbers are gone for good.
    Returns `None` when no section lists the id, so the caller can fall back to the
    fully-blank missing sentinel (`linked_signal_for_missing_id`).
    """
    symbol = find_symbol_for_signal_id(instrument_breakdown, signal_id)
    if symbol is None:
        return None
    return LinkedSignalResponse(
        signal_id=signal_id,
        symbol=symbol,
        impact=ImpactClass.UNCERTAIN.value,
        confidence=0.0,
        title="",
    )
