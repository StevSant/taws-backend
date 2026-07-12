from typing import Any

from app.infrastructure.realtime.tools.args import ListSignalsArgs


async def handle_list_signals(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    """Return the Analyst signals recorded for one instrument.

    Delegates to `SignalRepository.list_for_instrument`. Signals are Analyst-produced
    market observations, not per-user data (same visibility model as `GET /api/v1/signals`),
    so `user_id` is unused. Each signal is flattened to the fields the voice model
    narrates (impact/confidence/thesis), never the full evidence list.
    """
    typed: ListSignalsArgs = args
    symbol = typed.symbol.upper()

    repository = container.get_signal_repository()
    signals = await repository.list_for_instrument(symbol)

    return {
        "symbol": symbol,
        "count": len(signals),
        "signals": [
            {
                "id": signal.id,
                "impact_class": signal.impact_class.value,
                "confidence": signal.confidence,
                "thesis": signal.thesis,
                "created_at": signal.created_at.isoformat(),
            }
            for signal in signals
        ],
    }
