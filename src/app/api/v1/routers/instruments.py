from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import get_instrument_universe
from app.api.v1.schemas import InstrumentResponse
from app.domain.market.entities import AssetClass
from app.domain.market.ports import InstrumentUniverse

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("")
async def list_instruments(
    universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    asset_class: Annotated[AssetClass | None, Query()] = None,
) -> list[InstrumentResponse]:
    """List the curated instrument universe, optionally filtered by asset class."""
    instruments = universe.by_asset_class(asset_class) if asset_class else universe.all()
    return [InstrumentResponse.model_validate(instrument) for instrument in instruments]
