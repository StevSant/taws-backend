from dataclasses import dataclass

from app.application.quant.volatility_regime import VolatilityRegime
from app.domain.market.entities import AssetClass
from app.domain.signals.entities import Signal


@dataclass(frozen=True, slots=True)
class EnrichedInstrument:
    """An instrument row already enriched with market + signal data for the explorer.

    Produced by `ListEnrichedInstruments` so the markets-explorer page can render a full
    Binance-style row (price, 24h change, volatility, sparkline, latest AI signal) without
    fanning out one request per instrument per column. Every market-derived field is
    `None`/empty (never a crash) when the underlying price series is too thin to compute
    from — same graceful-degradation contract as `application.quant.MarketStats`.
    """

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    last_price: float | None
    price_delta_pct: float | None
    volatility_pct: float | None
    volatility_regime: VolatilityRegime | None
    sparkline: list[float]
    latest_signal: Signal | None
