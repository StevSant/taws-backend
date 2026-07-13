from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_generate_signal_use_case,
    get_signal_repository,
)
from app.api.v1.schemas import GenerateSignalRequest, SignalResponse
from app.application.compliance import ComplianceViolationError
from app.application.signals import InsufficientEvidenceError, UnknownInstrumentError
from app.application.signals.use_cases import GenerateSignal
from app.core.config import Settings, get_settings
from app.domain.signals.ports import SignalRepository

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    instrument: Annotated[str, Query()],
) -> list[SignalResponse]:
    """Return every signal recorded for an instrument (Radar UI).

    Not user-scoped (no `require_current_user`): a `Signal` is an Analyst-produced market
    observation about an instrument, not per-user data — same visibility model as
    `GET /api/v1/news`.
    """
    signals = await signal_repository.list_for_instrument(instrument.upper())
    return [SignalResponse.model_validate(s) for s in signals]


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_signal(
    payload: GenerateSignalRequest,
    use_case: Annotated[GenerateSignal, Depends(get_generate_signal_use_case)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SignalResponse:
    """Ensure a fresh Analyst signal exists for one instrument, and return it (HU1/HU2).

    Freshness-gated since issue #29: this endpoint now means "ensure fresh", not "always
    recompute". If a signal for `(instrument, locale)` is still within its asset class's TTL,
    it is returned as-is — no LLM run, no duplicate row. A `Signal` is shared, non-personalized
    analysis, so N clients asking about AAPL inside the TTL window should cost one LLM call.

    There is deliberately NO `force` query param: this endpoint is unauthenticated, and a
    client that could set `force=true` could trivially bust the cache and reintroduce exactly
    the cost the gate removes. Forcing is internal only (the background refresh job, and the
    per-article "Analizar ahora" button — see `ForceAnalyzeNewsItem`).

    Not user-scoped (no `require_current_user`): a `Signal` is an Analyst-produced market
    observation about an instrument, not per-user data — same visibility model as
    `GET /api/v1/news` and `GET /api/v1/instruments`.
    """
    try:
        locale = payload.locale or settings.default_locale
        signal = await use_case.execute(payload.instrument_symbol.upper(), locale)
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InsufficientEvidenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ComplianceViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return SignalResponse.model_validate(signal)
