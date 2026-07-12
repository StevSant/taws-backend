from datetime import datetime

from pydantic import BaseModel


class CandleResponse(BaseModel):
    """A single OHLC bar within `MarketStatsResponse.candles`.

    Compact wire keys (t,o,h,l,c,v) keep the candle array small for charting; `v`
    (volume) is optional because not every market-data source provides it.
    """

    t: datetime
    o: float
    h: float
    l: float  # noqa: E741 — 'l' is the OHLC "low" wire key, not an ambiguous variable
    c: float
    v: float | None
