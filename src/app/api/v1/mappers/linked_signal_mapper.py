from app.api.v1.schemas.linked_signal_response import LinkedSignalResponse
from app.domain.signals.entities import ImpactClass, Signal

# Placeholder for a linked signal id that no longer resolves to a persisted `Signal`
# (deleted/missing). The frontend treats this as "no radar target" and falls back.
_MISSING_SYMBOL = "—"


def linked_signal_from_signal(signal: Signal) -> LinkedSignalResponse:
    """Map a resolved `Signal` to its human-readable `LinkedSignalResponse`."""
    return LinkedSignalResponse(
        signal_id=signal.id,
        symbol=signal.instrument_symbol,
        impact=signal.impact_class.value,
        confidence=signal.confidence,
        title=signal.thesis,
    )


def linked_signal_for_missing_id(signal_id: str) -> LinkedSignalResponse:
    """Build a degraded `LinkedSignalResponse` for a linked signal id that no longer exists.

    Emitting a placeholder row (instead of dropping the id or raising) keeps the briefing
    renderable: the frontend sees the id, an "unknown" symbol, and neutral defaults.
    """
    return LinkedSignalResponse(
        signal_id=signal_id,
        symbol=_MISSING_SYMBOL,
        impact=ImpactClass.UNCERTAIN.value,
        confidence=0.0,
        title="",
    )
