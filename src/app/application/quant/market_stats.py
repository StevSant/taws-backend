from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.application.quant.unusual_move import UnusualMove
from app.application.quant.volatility_regime import VolatilityRegime


@dataclass(frozen=True, slots=True)
class MarketStats:
    """Result of `ComputeMarketStats.execute(...)`: price delta, volatility, unusual moves.

    Not persisted (no repository) — a computed-on-demand value object, same role as
    `application.signals.SignalClassification` for the Analyst pipeline. Every derived
    field is `None`/empty (never a crash) when the underlying price series is too short
    to compute from — see `ComputeMarketStats`'s docstring.
    """

    instrument_symbol: str
    window_days: int
    last_price: float | None
    price_delta_pct: float | None
    volatility_pct: float | None
    volatility_regime: VolatilityRegime | None
    unusual_moves: list[UnusualMove]
    as_of: datetime = field(default_factory=lambda: datetime.now(UTC))
