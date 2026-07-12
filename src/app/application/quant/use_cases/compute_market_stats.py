import statistics
from datetime import UTC, datetime

from app.application.quant.compute_daily_returns import compute_daily_returns
from app.application.quant.market_stats import MarketStats
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.application.quant.unusual_move import UnusualMove
from app.application.quant.volatility_regime import VolatilityRegime
from app.domain.market.entities import PriceCandle
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider

_DEFAULT_WINDOW_DAYS = 30

# Trading-day count used to annualize the window's daily-return stdev into a
# comparable "annualized volatility %" figure — the standard equities convention
# (252 trading days/year). Applied uniformly across asset classes (including crypto,
# which trades every day) as a documented T1 simplification; a per-asset-class
# calendar is out of scope here.
_ANNUALIZATION_TRADING_DAYS = 252

# Annualized-volatility % upper bounds for each `VolatilityRegime` bucket (generic
# equity-style bands, not calibrated per instrument/asset class — T1 simplification,
# see the class docstring below).
_VOL_REGIME_LOW_MAX_PCT = 15.0
_VOL_REGIME_NORMAL_MAX_PCT = 30.0
_VOL_REGIME_ELEVATED_MAX_PCT = 50.0

# A day's return z-score (against the window's own mean/stdev of daily returns) must
# exceed this to be flagged as an "unusual move" — the standard "beyond ~2 stdev"
# statistical threshold, not a fixed percentage, so it self-adjusts to each
# instrument's own recent volatility instead of penalizing naturally volatile assets
# (e.g. crypto) with an equities-calibrated cutoff.
_UNUSUAL_MOVE_Z_THRESHOLD = 2.0

# Caps how many unusual-move days are returned, so a long window on a volatile
# instrument doesn't blow up the tool/response payload — same bounding rationale as
# `generate_briefing.py`'s `_MAX_SIGNALS_IN_CONTEXT`.
_MAX_UNUSUAL_MOVES = 10


class ComputeMarketStats:
    """Quant pipeline: instrument price history -> price delta, volatility, unusual moves.

    Reusable core logic for issue #7 (Quant Analyst, T1). This is the ONLY place the
    price-delta/volatility/unusual-move math lives — the `quant` chat specialist's
    grounding tool (`infrastructure/agents/tools/get_market_stats_tool.py`) and the
    `GET /api/v1/quant/stats` endpoint (`api/v1/routers/quant.py`) both call
    `execute(...)` directly rather than duplicating it, and the future Scenario
    Simulation graph's quantification step (issue #12) can do the same. Same
    "reusable use case, not chat-tool-only logic" shape as `GenerateSignal`/
    `GenerateBriefing` — see `application/signals/use_cases/generate_signal.py`'s
    docstring for the precedent.

    Constructor-injected with `MarketDataProvider` + `InstrumentUniverse` (both
    existing ports — no new port method was needed: `MarketDataProvider.
    get_price_series` already returns the OHLC candles this computes from).

    Degrades gracefully rather than raising on thin data: `RoutingMarketDataProvider`
    already falls back to the deterministic `FixtureMarketDataProvider` on any live
    -source failure or empty result, so a `PriceSeries` is effectively always
    available; if it's still too short to compute a given statistic from (fewer than
    2 candles for price delta, fewer than 3 for volatility/unusual moves), that
    field is `None`/empty in the returned `MarketStats` instead of raising. Only an
    unknown instrument symbol raises (`UnknownInstrumentError`).

    Volatility regime and unusual-move detection are both documented T1
    simplifications (see the module-level threshold constants above): generic
    annualized-volatility bands and a z-score-based move flag, not a per-asset-class
    calibrated model.
    """

    def __init__(
        self, market_data_provider: MarketDataProvider, instrument_universe: InstrumentUniverse
    ) -> None:
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe

    async def execute(
        self, instrument_symbol: str, window_days: int = _DEFAULT_WINDOW_DAYS
    ) -> MarketStats:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        series = await self._market_data_provider.get_price_series(instrument, window_days)
        candles = series.candles
        return_pairs = compute_daily_returns(candles)

        volatility_pct = _annualized_volatility_pct(return_pairs)

        return MarketStats(
            instrument_symbol=instrument.symbol,
            window_days=window_days,
            last_price=candles[-1].close if candles else None,
            price_delta_pct=_price_delta_pct(candles),
            volatility_pct=volatility_pct,
            volatility_regime=_classify_volatility_regime(volatility_pct),
            unusual_moves=_detect_unusual_moves(return_pairs),
            candles=candles,
            as_of=datetime.now(UTC),
        )


def _price_delta_pct(candles: list[PriceCandle]) -> float | None:
    """Percentage change from the window's first close to its last close."""
    if len(candles) < 2 or candles[0].close == 0:
        return None
    first, last = candles[0], candles[-1]
    return round((last.close - first.close) / first.close * 100, 4)


def _annualized_volatility_pct(return_pairs: list[tuple[PriceCandle, float]]) -> float | None:
    """Population stdev of daily returns, annualized to `_ANNUALIZATION_TRADING_DAYS`."""
    if len(return_pairs) < 2:
        return None
    daily_stdev = statistics.pstdev(pct_return for _, pct_return in return_pairs)
    return round(daily_stdev * (_ANNUALIZATION_TRADING_DAYS**0.5), 4)


def _classify_volatility_regime(volatility_pct: float | None) -> VolatilityRegime | None:
    if volatility_pct is None:
        return None
    if volatility_pct <= _VOL_REGIME_LOW_MAX_PCT:
        return VolatilityRegime.LOW
    if volatility_pct <= _VOL_REGIME_NORMAL_MAX_PCT:
        return VolatilityRegime.NORMAL
    if volatility_pct <= _VOL_REGIME_ELEVATED_MAX_PCT:
        return VolatilityRegime.ELEVATED
    return VolatilityRegime.HIGH


def _detect_unusual_moves(return_pairs: list[tuple[PriceCandle, float]]) -> list[UnusualMove]:
    if len(return_pairs) < 2:
        return []
    daily_returns = [pct_return for _, pct_return in return_pairs]
    mean_return = statistics.mean(daily_returns)
    stdev_return = statistics.pstdev(daily_returns)
    if stdev_return == 0:
        return []

    moves: list[UnusualMove] = []
    for candle, daily_return in return_pairs:
        z_score = (daily_return - mean_return) / stdev_return
        if abs(z_score) >= _UNUSUAL_MOVE_Z_THRESHOLD:
            moves.append(
                UnusualMove(
                    date=candle.timestamp,
                    return_pct=round(daily_return, 4),
                    z_score=round(z_score, 2),
                )
            )
    return moves[-_MAX_UNUSUAL_MOVES:]
