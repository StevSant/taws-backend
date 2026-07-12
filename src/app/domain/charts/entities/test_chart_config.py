"""Regression tests for `ChartConfig.fetch_days_for_range` — how wide a trailing window to
fetch so a custom range reaching back to `from_date` is covered, capped at `max_days`.

The pre-push review flagged the `span = (today - from_date).days + 1` arithmetic (off-by-one
risk) and the `max_days` cap as refactor-fragile and untested. These pin the inclusive span,
the never-below-one clamp for future dates, and the cap.
"""

from datetime import date

from app.domain.charts.entities import ChartConfig


def _config() -> ChartConfig:
    return ChartConfig(
        default_timeframe="1y",
        max_points=500,
        available_timeframes=["1m", "1y", "max"],
        timeframe_days={"1m": 30, "1y": 365, "max": 1825},
    )


def test_same_day_range_fetches_one_day():
    cfg = _config()
    assert cfg.fetch_days_for_range(date(2026, 2, 15), today=date(2026, 2, 15)) == 1


def test_span_is_inclusive_of_both_ends():
    cfg = _config()
    # 2026-02-10 .. 2026-02-15 span five calendar days apart => inclusive window of 6.
    assert cfg.fetch_days_for_range(date(2026, 2, 10), today=date(2026, 2, 15)) == 6


def test_future_from_date_never_returns_less_than_one():
    cfg = _config()
    # from_date after today yields a negative delta; must clamp to at least 1, never 0/negative.
    assert cfg.fetch_days_for_range(date(2026, 3, 1), today=date(2026, 2, 1)) == 1


def test_range_older_than_max_window_is_capped_at_max_days():
    cfg = _config()  # widest configured window is 1825 days
    assert cfg.fetch_days_for_range(date(2000, 1, 1), today=date(2026, 2, 1)) == 1825
