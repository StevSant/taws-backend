from app.api.v1.schemas import CandleResponse
from app.domain.market.entities import PriceCandle


def map_price_candle_to_candle_response(candle: PriceCandle) -> CandleResponse:
    """Map a domain `PriceCandle` to the API `CandleResponse` (compact OHLC wire keys).

    Keeps the domain entity out of the response layer: the API's compact keys
    (t,o,h,l,c,v) are decided here, not leaked from `PriceCandle`'s field names.
    """
    return CandleResponse(
        t=candle.timestamp,
        o=candle.open,
        h=candle.high,
        l=candle.low,
        c=candle.close,
        v=candle.volume,
    )
