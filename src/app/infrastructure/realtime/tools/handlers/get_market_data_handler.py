from typing import Any

from app.infrastructure.realtime.tools.args import GetMarketDataArgs
from app.infrastructure.realtime.tools.unknown_instrument_tool_error import (
    UnknownInstrumentToolError,
)


async def handle_get_market_data(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    """Return the latest price + recent series for one instrument.

    Delegates to `MarketDataProvider.get_last_price` / `get_price_series`, resolving the
    symbol through the curated `InstrumentUniverse` first (so only tracked instruments
    are queryable). `user_id` is unused here — market data is public, not per-user — but
    is part of the uniform handler signature.
    """
    typed: GetMarketDataArgs = args
    symbol = typed.symbol.upper()
    universe = container.get_instrument_universe()
    instrument = universe.by_symbol(symbol)
    if instrument is None:
        raise UnknownInstrumentToolError(symbol)

    provider = container.get_market_data_provider()
    last_price = await provider.get_last_price(instrument)
    series = await provider.get_price_series(instrument, days=typed.days)

    return {
        "symbol": instrument.symbol,
        "name": instrument.name,
        "asset_class": instrument.asset_class.value,
        "currency": instrument.currency,
        "last_price": last_price,
        "series": [
            {"timestamp": candle.timestamp.isoformat(), "close": candle.close}
            for candle in series.candles
        ],
    }
