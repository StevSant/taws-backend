import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_macro_data_provider
from app.api.v1.schemas import MacroStateResponse
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
