from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.signal_response import SignalResponse
from app.application.quant.volatility_regime import VolatilityRegime
from app.domain.market.entities import AssetClass


class EnrichedInstrumentResponse(BaseModel):
    """One markets-explorer row: instrument identity + market metrics + latest AI signal.

    Every market-derived field is nullable and `sparkline` may be empty when the underlying
    price series is too thin — the frontend renders a muted/"sin datos" state rather than a
    crash. `sparkline` is a downsampled list of closing prices (oldest -> newest).
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    last_price: float | None
    price_delta_pct: float | None
    volatility_pct: float | None
    volatility_regime: VolatilityRegime | None
    sparkline: list[float]
    latest_signal: SignalResponse | None
