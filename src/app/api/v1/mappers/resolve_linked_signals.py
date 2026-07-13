from app.api.v1.mappers.linked_signal_mapper import (
    linked_signal_for_missing_id,
    linked_signal_from_signal,
)
from app.api.v1.schemas.linked_signal_response import LinkedSignalResponse
from app.domain.signals.ports import SignalRepository


async def resolve_linked_signals(
    signal_ids: list[str], signal_repository: SignalRepository
) -> list[LinkedSignalResponse]:
    """Resolve a briefing's `linked_signal_ids` to human-readable `LinkedSignalResponse`s.

    The `SignalRepository` port exposes only single-id `get(...)` (no batch lookup), so
    this loops one `get()` per id. The loop is bounded by the number of signals linked to
    a single briefing (a small, watchlist-scoped set), so it is not an open-ended N+1; if
    a batch `get_by_ids` is ever added to the port, swap the loop for it here only.

    Ids that no longer resolve to a persisted signal (deleted/missing) degrade gracefully
    to a placeholder row rather than being dropped or raising, so the briefing stays
    renderable and the frontend can fall back.
    """
    resolved: list[LinkedSignalResponse] = []
    for signal_id in signal_ids:
        signal = await signal_repository.get(signal_id)
        if signal is None:
            resolved.append(linked_signal_for_missing_id(signal_id))
        else:
            resolved.append(linked_signal_from_signal(signal))
    return resolved
