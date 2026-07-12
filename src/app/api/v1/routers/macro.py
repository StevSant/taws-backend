import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.dependencies import get_interpret_macro_event_use_case, get_macro_data_provider
from app.api.v1.schemas import (
    InterpretMacroEventRequest,
    MacroEventInterpretationResponse,
    MacroSeriesResponse,
    MacroStateResponse,
)
from app.application.macro.use_cases import InterpretMacroEvent
from app.core.config import Settings, get_settings
from app.domain.market.entities import MacroIndicator
from app.domain.market.ports import MacroDataProvider

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("")
async def get_macro_state(
    macro_data_provider: Annotated[MacroDataProvider, Depends(get_macro_data_provider)],
) -> MacroStateResponse:
    """Return current macro state (issue #15): FRED rates + CPI, and the VIX-derived
    volatility regime. Not instrument-scoped — same market-wide visibility model as
    `GET /api/v1/news`.
    """
    rates, cpi, volatility = await asyncio.gather(
        macro_data_provider.get_rates(),
        macro_data_provider.get_cpi(),
        macro_data_provider.get_volatility_regime(),
    )
    return MacroStateResponse.model_validate({"rates": rates, "cpi": cpi, "volatility": volatility})


@router.get("/series/{indicator}")
async def get_macro_series(
    indicator: MacroIndicator,
    macro_data_provider: Annotated[MacroDataProvider, Depends(get_macro_data_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int | None, Query(ge=2)] = None,
) -> MacroSeriesResponse:
    """Return an indicator's recent history for the "Contexto de mercado" sparklines (#58).

    Covers rates/CPI plus gold, oil and the 10Y Treasury yield. `days` bounds the window
    (clamped to the configured max); omit it for the configured default. Not user-scoped —
    same market-wide visibility model as `GET /api/v1/macro`.
    """
    resolved_days = min(days or settings.macro_series_default_days, settings.macro_series_max_days)
    series = await macro_data_provider.get_indicator_history(indicator, resolved_days)
    return MacroSeriesResponse.model_validate(series)


@router.post("/interpret", status_code=status.HTTP_201_CREATED)
async def interpret_macro_event(
    payload: InterpretMacroEventRequest,
    use_case: Annotated[InterpretMacroEvent, Depends(get_interpret_macro_event_use_case)],
) -> MacroEventInterpretationResponse:
    """Trigger the Macro Analyst on-demand for one event (issue #21): tags every asset
    class with a direction + magnitude, grounded in the real current FRED/VIX state.

    Not user-scoped (no `require_current_user`) — same market-wide visibility model as
    `GET /api/v1/macro` and `POST /api/v1/consequence-chains/generate`. `event_description`
    is optional; omitting it interprets the current macro state generally. Never raises:
    `InterpretMacroEvent` degrades to a fallback interpretation instead of erroring when
    structured output is unavailable, so this endpoint always returns `201`.
    """
    interpretation = await use_case.execute(payload.event_description)
    return MacroEventInterpretationResponse.model_validate(interpretation)
