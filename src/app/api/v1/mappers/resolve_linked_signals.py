from app.api.v1.mappers.linked_signal_breakdown_fallback import linked_signal_from_breakdown
from app.api.v1.mappers.linked_signal_mapper import (
    linked_signal_for_missing_id,
    linked_signal_from_signal,
)
from app.api.v1.schemas.linked_signal_response import LinkedSignalResponse
from app.domain.briefing.entities import BriefingInstrumentSection
from app.domain.signals.ports import SignalRepository


async def resolve_linked_signals(
    signal_ids: list[str],
    signal_repository: SignalRepository,
    instrument_breakdown: list[BriefingInstrumentSection],
) -> list[LinkedSignalResponse]:
    """Resolve a briefing's `linked_signal_ids` to human-readable `LinkedSignalResponse`s.

    One `get_by_ids` batch call resolves every id at once (replacing the old
    one-`get()`-per-id loop). Ids the repository no longer has — retention
    (`prune_for_instrument`) deletes signal rows while briefings keep referencing
    them — degrade in two steps rather than one:

    1. if a `instrument_breakdown` section still lists the id, a partial row with
       the section's real `symbol` (neutral impact/confidence) keeps the frontend's
       `/radar/{symbol}` link working;
    2. only an id in neither place falls back to the fully-blank "—" sentinel.

    Ids are never dropped and never raise, so the briefing stays renderable.
    """
    if not signal_ids:
        return []
    signals = await signal_repository.get_by_ids(signal_ids)
    resolved: list[LinkedSignalResponse] = []
    for signal_id in signal_ids:
        signal = signals.get(signal_id)
        if signal is not None:
            resolved.append(linked_signal_from_signal(signal))
            continue
        fallback = linked_signal_from_breakdown(signal_id, instrument_breakdown)
        resolved.append(
            fallback if fallback is not None else linked_signal_for_missing_id(signal_id)
        )
    return resolved
