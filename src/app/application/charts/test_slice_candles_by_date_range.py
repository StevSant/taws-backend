"""Regression tests for `slice_candles_by_date_range` — inclusive `[from, to]` slicing of the
fetched candle window when a custom chart range is supplied.

The pre-push review flagged this branch (empty list, range fully outside the data,
boundary-inclusive dates, open-ended bounds) as refactor-fragile and untested. These lock in
the inclusive bounds, the both-`None` passthrough, and the empty-window behavior.
"""

from datetime import UTC, date, datetime

from app.application.charts.slice_candles_by_date_range import slice_candles_by_date_range
from app.domain.market.entities import PriceCandle


def _candle(day: int) -> PriceCandle:
    return PriceCandle(
        timestamp=datetime(2026, 2, day, 14, 30, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
    )


def test_returns_all_candles_unchanged_when_both_bounds_are_none():
    candles = [_candle(1), _candle(2), _candle(3)]
    assert slice_candles_by_date_range(candles, None, None) == candles


def test_returns_empty_for_empty_input():
    assert slice_candles_by_date_range([], date(2026, 2, 1), date(2026, 2, 28)) == []


def test_includes_both_boundary_dates():
    candles = [_candle(1), _candle(2), _candle(3), _candle(4)]
    result = slice_candles_by_date_range(candles, date(2026, 2, 2), date(2026, 2, 3))
    assert result == [_candle(2), _candle(3)]


def test_matches_on_calendar_date_ignoring_intraday_time():
    # Candles carry a 14:30 UTC time; a plain YYYY-MM-DD bound must still match the day.
    candles = [_candle(2)]
    assert slice_candles_by_date_range(candles, date(2026, 2, 2), date(2026, 2, 2)) == candles


def test_returns_empty_when_range_is_entirely_before_the_data():
    candles = [_candle(10), _candle(11)]
    assert slice_candles_by_date_range(candles, date(2026, 1, 1), date(2026, 1, 31)) == []


def test_returns_empty_when_range_is_entirely_after_the_data():
    candles = [_candle(1), _candle(2)]
    assert slice_candles_by_date_range(candles, date(2026, 3, 1), date(2026, 3, 31)) == []


def test_open_ended_from_only_keeps_candles_on_or_after():
    candles = [_candle(1), _candle(2), _candle(3)]
    assert slice_candles_by_date_range(candles, date(2026, 2, 2), None) == [_candle(2), _candle(3)]


def test_open_ended_to_only_keeps_candles_on_or_before():
    candles = [_candle(1), _candle(2), _candle(3)]
    assert slice_candles_by_date_range(candles, None, date(2026, 2, 2)) == [_candle(1), _candle(2)]
