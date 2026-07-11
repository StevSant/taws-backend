from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OhlcBar:
    """A single OHLC bar for a candlestick series. `t` is an ISO-8601 timestamp string.
    `v` (volume) is optional — not every source provides it."""

    t: str
    o: float
    h: float
    l: float  # noqa: E741 — OHLC wire field; renaming would break the wire contract
    c: float
    v: float | None = None
