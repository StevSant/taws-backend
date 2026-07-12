from typing import Any

from app.infrastructure.realtime.tools.args import GenerateSignalArgs


async def handle_generate_signal(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    """Run the Analyst pipeline on-demand for one instrument and return the new signal.

    Delegates to the exact same `GenerateSignal.execute(symbol, locale)` the
    `POST /api/v1/signals/generate` endpoint runs (built via
    `Container.get_generate_signal_use_case`). A `Signal` is a market observation, not
    per-user data, so `user_id` is unused. `UnknownInstrumentError` /
    `InsufficientEvidenceError` / `ComplianceViolationError` propagate to the endpoint,
    which turns them into a recoverable structured error output for the voice model.
    """
    typed: GenerateSignalArgs = args
    symbol = typed.symbol.upper()
    locale = typed.locale or container._settings.default_locale

    use_case = container.get_generate_signal_use_case()
    signal = await use_case.execute(symbol, locale)

    return {
        "id": signal.id,
        "symbol": signal.instrument_symbol,
        "impact_class": signal.impact_class.value,
        "confidence": signal.confidence,
        "thesis": signal.thesis,
        "key_drivers": signal.key_drivers,
        "risk_factors": signal.risk_factors,
        "analysis_available": signal.analysis_available,
    }
