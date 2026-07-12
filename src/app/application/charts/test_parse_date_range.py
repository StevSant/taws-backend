"""Regression tests for `parse_date_range` — the guard that keeps a bad custom chart range
from erroring the request. A missing, malformed, or out-of-order range must degrade to the
timeframe preset (return `None`), never raise.

The pre-push review flagged that the "never a hard error" contract was enforced only by an
untested `try/except`, and that a syntactically-valid-but-calendar-invalid date like
`2026-13-45` (which passes the schema's `^\\d{4}-\\d{2}-\\d{2}$` regex) reaches this function
unguarded. These lock the contract in.

Per `backend/CLAUDE.md`: a minimal regression test next to bug-prone logic, not a suite.
"""

from datetime import date

from app.application.charts.parse_date_range import parse_date_range


def test_returns_parsed_tuple_for_a_valid_ordered_range():
    assert parse_date_range("2026-01-01", "2026-03-31") == (date(2026, 1, 1), date(2026, 3, 31))


def test_allows_equal_from_and_to_dates():
    assert parse_date_range("2026-02-15", "2026-02-15") == (date(2026, 2, 15), date(2026, 2, 15))


def test_returns_none_when_from_date_is_missing():
    assert parse_date_range(None, "2026-03-31") is None


def test_returns_none_when_to_date_is_missing():
    assert parse_date_range("2026-01-01", None) is None


def test_returns_none_when_both_bounds_are_none():
    assert parse_date_range(None, None) is None


def test_returns_none_for_empty_string_bounds():
    assert parse_date_range("", "") is None


def test_returns_none_when_range_is_reversed():
    assert parse_date_range("2026-03-31", "2026-01-01") is None


def test_returns_none_for_calendar_invalid_date_that_passes_the_regex():
    # "2026-13-45" satisfies ^\d{4}-\d{2}-\d{2}$ but is not a real calendar date; the schema
    # regex lets it through, so this function's try/except is the only thing preventing a 500.
    assert parse_date_range("2026-13-45", "2026-12-31") is None


def test_returns_none_for_non_iso_garbage():
    assert parse_date_range("not-a-date", "also-bad") is None
