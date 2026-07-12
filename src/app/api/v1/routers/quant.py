from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import get_instrument_universe, get_market_data_provider
from app.api.v1.mappers import map_price_candle_to_candle_response
from app.api.v1.schemas import EventStudyResponse, MarketStatsResponse, UnusualMoveResponse
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.application.quant.use_cases import ComputeEventStudy, ComputeMarketStats
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider

router = APIRouter(prefix="/quant", tags=["quant"])

_DEFAULT_WINDOW_DAYS = 30
_DEFAULT_LOOKBACK_DAYS = 365
_DEFAULT_MOVE_THRESHOLD_PCT = 3.0
_MAX_DAYS = 365


@router.get("/stats")
async def get_market_stats(
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    instrument: Annotated[str, Query(min_length=1, max_length=20)],
    window_days: Annotated[int, Query(ge=2, le=_MAX_DAYS)] = _DEFAULT_WINDOW_DAYS,
) -> MarketStatsResponse:
    """Quant Analyst (issue #7): price delta, volatility regime, unusual-move flags.

    Not user-scoped (no `require_current_user`): `MarketStats` is computed on-demand
    from `MarketDataProvider`, not per-user data — same visibility model as
    `GET /api/v1/news` / `GET /api/v1/instruments` and `POST /api/v1/signals/generate`.
    Reachable independently of chat so a non-chat integration (or the future Scenario
    Simulation graph, issue #12) can call the same `ComputeMarketStats` use case.
    """
    use_case = ComputeMarketStats(
        market_data_provider=market_data_provider, instrument_universe=instrument_universe
    )
    try:
        stats = await use_case.execute(instrument.upper(), window_days)
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # `candles` is mapped explicitly (domain PriceCandle -> compact OHLC schema); every
    # other field maps by name via `from_attributes`.
    return MarketStatsResponse(
        instrument_symbol=stats.instrument_symbol,
        window_days=stats.window_days,
        last_price=stats.last_price,
        price_delta_pct=stats.price_delta_pct,
        volatility_pct=stats.volatility_pct,
        volatility_regime=stats.volatility_regime,
        unusual_moves=[UnusualMoveResponse.model_validate(m) for m in stats.unusual_moves],
        candles=[map_price_candle_to_candle_response(c) for c in stats.candles],
        as_of=stats.as_of,
    )


@router.get("/event-study")
async def get_event_study_stats(
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    instrument: Annotated[str, Query(min_length=1, max_length=20)],
    lookback_days: Annotated[int, Query(ge=2, le=_MAX_DAYS)] = _DEFAULT_LOOKBACK_DAYS,
    move_threshold_pct: Annotated[float, Query(gt=0)] = _DEFAULT_MOVE_THRESHOLD_PCT,
) -> EventStudyResponse:
    """Quant Analyst (issue #7): "last N similar events" median/range statistics.

    See `get_market_stats` above for the visibility/reuse rationale — same shape here,
    backed by `ComputeEventStudy` instead of `ComputeMarketStats`.
    """
    use_case = ComputeEventStudy(
        market_data_provider=market_data_provider, instrument_universe=instrument_universe
    )
    try:
        stats = await use_case.execute(instrument.upper(), lookback_days, move_threshold_pct)
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return EventStudyResponse.model_validate(stats)
