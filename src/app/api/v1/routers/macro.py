import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import get_interpret_macro_event_use_case, get_macro_data_provider
from app.api.v1.schemas import (
    InterpretMacroEventRequest,
    MacroEventInterpretationResponse,
    MacroStateResponse,
)
from app.application.macro.use_cases import InterpretMacroEvent
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
