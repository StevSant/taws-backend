from app.domain.market.entities import PriceCandle


def downsample_candles(candles: list[PriceCandle], max_points: int) -> list[PriceCandle]:
    """Evenly thin a candle list to at most `max_points`, always keeping the last candle.

    Prevents a long intraday/`max` window from shipping thousands of points to the browser
    (see `Settings.chart_max_points`). Uniform stride sampling — good enough for a visual
    overview; not a statistical resample."""
    if max_points <= 0 or len(candles) <= max_points:
        return candles
    stride = len(candles) / max_points
    sampled = [candles[int(index * stride)] for index in range(max_points)]
    if sampled[-1] is not candles[-1]:
        sampled[-1] = candles[-1]
    return sampled
