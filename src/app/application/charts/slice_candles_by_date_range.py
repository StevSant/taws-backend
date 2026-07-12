from datetime import date

from app.domain.market.entities import PriceCandle


def slice_candles_by_date_range(
    candles: list[PriceCandle],
    from_date: date | None,
    to_date: date | None,
) -> list[PriceCandle]:
    """Filter candles to the inclusive `[from_date, to_date]` window (either bound optional).

    The market-data port only fetches by a day count (no native start/end), so a custom
    range is served by fetching a wide-enough window upstream and slicing it here. Bounds
    are compared on the candle's calendar date, so intraday timestamps still match a plain
    `YYYY-MM-DD` bound. An out-of-order or empty range is the caller's responsibility to
    reject before calling this; with both bounds `None` the list is returned unchanged."""
    if from_date is None and to_date is None:
        return candles
    return [
        candle
        for candle in candles
        if (from_date is None or candle.timestamp.date() >= from_date)
        and (to_date is None or candle.timestamp.date() <= to_date)
    ]
