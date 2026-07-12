import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_instrument_universe,
    get_market_data_provider,
    get_register_instrument_use_case,
    get_search_coins_use_case,
    get_signal_repository,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.schemas import (
    CoinCandidateResponse,
    CurrentUser,
    InstrumentPageResponse,
    InstrumentResponse,
    InstrumentSearchResponse,
    RegisterInstrumentRequest,
    RegisterInstrumentResponse,
)
from app.application.instruments import InstrumentSortField, SortDirection
from app.application.instruments.errors import SymbolCollisionError
from app.application.instruments.use_cases import (
    ListEnrichedInstruments,
    RegisterInstrument,
    SearchCoins,
)
from app.domain.market.entities import AssetClass, CoinCandidate
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.entities import Watchlist
from app.domain.watchlist.ports import WatchlistRepository

router = APIRouter(prefix="/instruments", tags=["instruments"])

_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_DEFAULT_WINDOW_DAYS = 30
_MAX_WINDOW_DAYS = 365
_SEARCH_MAX_LEN = 40
_DEFAULT_WATCHLIST_NAME = "My Watchlist"


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


@router.get("/search")
async def search_instruments(
    search_coins: Annotated[SearchCoins, Depends(get_search_coins_use_case)],
    q: Annotated[str, Query(min_length=1, max_length=_SEARCH_MAX_LEN)],
) -> InstrumentSearchResponse:
    """Resolve arbitrary crypto name/ticker queries against CoinGecko (issue #60).

    Ranked candidates the user can pick from before calling `POST /instruments` to
    register one. Returns `[]` on no hits or a soft CoinGecko failure (search never
    errors the request — instrument-search spec's "fails soft").
    """
    candidates = await search_coins.execute(q)
    return [CoinCandidateResponse.model_validate(candidate) for candidate in candidates]


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_instrument(
    payload: RegisterInstrumentRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    register_instrument_use_case: Annotated[
        RegisterInstrument, Depends(get_register_instrument_use_case)
    ],
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> RegisterInstrumentResponse:
    """Turn a resolved CoinGecko candidate into a real, globally visible instrument
    and add it to the caller's own watchlist in one action (issue #60).

    Outcomes (design's FIX #5): **201** full success; **409** the resolved symbol
    already exists under a different asset class (e.g. `COIN` the stock) — no write,
    body carries the untouched existing instrument; **502** the catalog/universe
    writes succeeded but the subsequent watchlist add failed — body carries the
    persisted instrument with `watchlisted: false` (the client can retry via the
    existing `POST /watchlists/{id}/items`).
    """
    candidate = CoinCandidate(
        id=payload.coingecko_id,
        symbol=payload.symbol,
        name=payload.name,
        market_cap_rank=None,
        thumb="",
    )
    watchlist_id = await _resolve_owned_watchlist_id(user, watchlist_repository)

    try:
        result = await register_instrument_use_case.execute(
            candidate=candidate, watchlist_id=watchlist_id
        )
    except SymbolCollisionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Symbol {error.symbol!r} already exists as a different asset class",
                "instrument": InstrumentResponse.model_validate(
                    error.existing_instrument
                ).model_dump(mode="json"),
            },
        ) from error

    response = RegisterInstrumentResponse.model_validate(result)
    if not result.watchlisted:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=response.model_dump(mode="json"),
        )
    return response


async def _resolve_owned_watchlist_id(
    user: CurrentUser, watchlist_repository: WatchlistRepository
) -> str:
    """Return the id of the calling user's watchlist, creating a default one on
    first use — mirrors the frontend's existing "Agregar instrumento" fallback
    (`AddInstrumentStore.ensureWatchlistId`): every user is assumed to track one
    watchlist for this quick-register flow.
    """
    existing = await watchlist_repository.list_for_user(user.id)
    if existing:
        return existing[0].id
    created = await watchlist_repository.create(
        Watchlist(id=str(uuid.uuid4()), user_id=user.id, name=_DEFAULT_WATCHLIST_NAME)
    )
    return created.id
