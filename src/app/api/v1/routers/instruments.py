from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import (
    get_instrument_universe,
    get_market_data_provider,
    get_signal_repository,
)
from app.api.v1.schemas import InstrumentPageResponse, InstrumentResponse
from app.application.instruments import InstrumentSortField, SortDirection
from app.application.instruments.use_cases import ListEnrichedInstruments
from app.domain.market.entities import AssetClass
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.domain.signals.ports import SignalRepository

router = APIRouter(prefix="/instruments", tags=["instruments"])

_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_DEFAULT_WINDOW_DAYS = 30
_MAX_WINDOW_DAYS = 365
_SEARCH_MAX_LEN = 40


@router.get("")
async def list_instruments(
    universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    asset_class: Annotated[AssetClass | None, Query()] = None,
) -> list[InstrumentResponse]:
    """List the curated instrument universe, optionally filtered by asset class.

    Lightweight identity-only listing (symbol/name/asset_class/currency) — used by the navbar
    search and the "Agregar instrumento" picker (issue #60). For the markets explorer's
    enriched rows (price/change/volatility/sparkline/signal), use `GET /instruments/enriched`.
    """
    instruments = universe.by_asset_class(asset_class) if asset_class else universe.all()
    return [InstrumentResponse.model_validate(instrument) for instrument in instruments]


@router.get("/enriched")
async def list_enriched_instruments(
    universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    asset_class: Annotated[AssetClass | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=_SEARCH_MAX_LEN)] = None,
    sort_by: Annotated[InstrumentSortField, Query()] = InstrumentSortField.NAME,
    sort_dir: Annotated[SortDirection, Query()] = SortDirection.ASC,
    page: Annotated[int, Query(ge=1)] = _DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = _DEFAULT_PAGE_SIZE,
    window_days: Annotated[int, Query(ge=2, le=_MAX_WINDOW_DAYS)] = _DEFAULT_WINDOW_DAYS,
) -> InstrumentPageResponse:
    """Paginated/filterable/sortable enriched instruments listing for the markets explorer.

    Each row already carries price, % change, volatility, a downsampled sparkline series and
    the latest AI signal, plus highlight leaderboards (top gainers/losers/most volatile/
    trending) — so the explorer page (issue #59) renders without fanning out one request per
    instrument per column (cf. the #44 N+1 warning). The server does one bounded concurrent
    fan-out over the small curated universe instead.
    """
    use_case = ListEnrichedInstruments(
        instrument_universe=universe,
        market_data_provider=market_data_provider,
        signal_repository=signal_repository,
    )
    page_result = await use_case.execute(
        asset_class=asset_class,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )
    return InstrumentPageResponse.model_validate(page_result)
