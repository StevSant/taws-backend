from app.domain.market.entities import PriceCandle


def compute_daily_returns(candles: list[PriceCandle]) -> list[tuple[PriceCandle, float]]:
    """Return `(candle, pct_return)` pairs for each close-over-close daily return, in order.

    Each pair's `candle` is the LATER of the two consecutive candles the return was
    computed from (i.e. the day the move happened on) — callers read the event's date
    off this candle rather than re-zipping the result against the original `candles`
    list, because the two are not guaranteed to stay the same length (see below).

    Shared by `ComputeMarketStats` and `ComputeEventStudy` (both use cases need the same
    daily-return series) — kept as one public helper instead of duplicated private logic
    in each use case file. Empty list if `candles` has fewer than 2 entries. A pair whose
    previous close is `0` is skipped (its return would be a divide-by-zero) rather than
    raising, so one bad data point never crashes the caller — this is exactly why the
    date travels with each return instead of being re-derived by index/position.
    """
    pairs: list[tuple[PriceCandle, float]] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        if previous.close == 0:
            continue
        pairs.append((current, (current.close - previous.close) / previous.close * 100))
    return pairs
