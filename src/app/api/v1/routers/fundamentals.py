from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import get_fundamentals_provider, get_instrument_universe
from app.api.v1.schemas import FundamentalsResponse
from app.domain.market.ports import FundamentalsProvider, InstrumentUniverse

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])


@router.get("/{symbol}")
async def get_fundamentals(
    symbol: str,
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    fundamentals_provider: Annotated[FundamentalsProvider, Depends(get_fundamentals_provider)],
) -> FundamentalsResponse:
    """Return `symbol`'s basic fundamentals plus earnings calendar / "upcoming earnings risk"
    tagging (issue #15). Not user-scoped — same market-wide visibility model as
    `GET /api/v1/news`.
    """
    instrument = instrument_universe.by_symbol(symbol)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown instrument: {symbol!r}"
        )

    fundamentals = await fundamentals_provider.get_fundamentals(instrument.symbol)
    earnings = await fundamentals_provider.get_earnings_calendar(instrument.symbol)
    return FundamentalsResponse.model_validate({"fundamentals": fundamentals, "earnings": earnings})
