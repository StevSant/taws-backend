import asyncio
from dataclasses import dataclass

import yfinance as yf

from app.domain.sentiment.entities import FearGreedReading
from app.domain.sentiment.errors import FearGreedUnavailableError
from app.infrastructure.sentiment.cnn_fear_greed_provider import CnnFearGreedProvider

_INDEX_TICKERS: tuple[tuple[str, str], ...] = (
    ("SPY", "S&P 500 (SPY)"),
    ("QQQ", "Nasdaq (QQQ)"),
    ("DIA", "Dow (DIA)"),
)


@dataclass(frozen=True, slots=True)
class MarketIndexQuote:
    symbol: str
    label: str
    price: float
    change_pct: float


@dataclass(frozen=True, slots=True)
class MarketPulseSnapshot:
    fear_greed: FearGreedReading
    delta_points: float
    market: str
    source: str
    indices: tuple[MarketIndexQuote, ...]


class GetMarketPulse:
    """Radar-facing market pulse: CNN stock Fear & Greed + major index quotes."""

    def __init__(self, cnn_provider: CnnFearGreedProvider) -> None:
        self._cnn_provider = cnn_provider

    async def execute(self) -> MarketPulseSnapshot:
        fear_greed, delta_points = await self._fetch_fear_greed()
        indices = await asyncio.to_thread(_fetch_index_quotes)
        return MarketPulseSnapshot(
            fear_greed=fear_greed,
            delta_points=delta_points,
            market="stock",
            source="cnn",
            indices=indices,
        )

    async def _fetch_fear_greed(self) -> tuple[FearGreedReading, float]:
        """The real CNN reading, or nothing. A fixture here is an invented market mood.

        This used to swallow the failure and return a `FixtureFearGreedReading` with a
        `delta_points` of 0.0 — a fabricated sentiment score, rendered to the user as a
        gauge and labelled `source="cnn"`, which CNN had never published.
        """
        try:
            return await self._cnn_provider.fetch_snapshot()
        except Exception as error:
            raise FearGreedUnavailableError(str(error)) from error


def _fetch_index_quotes() -> tuple[MarketIndexQuote, ...]:
    quotes: list[MarketIndexQuote] = []
    for symbol, label in _INDEX_TICKERS:
        quote = _fetch_quote(symbol, label)
        if quote is not None:
            quotes.append(quote)
    return tuple(quotes)


def _fetch_quote(symbol: str, label: str) -> MarketIndexQuote | None:
    try:
        history = yf.Ticker(symbol).history(period="5d")
        if history.empty or len(history) < 2:
            return None
        close = float(history["Close"].iloc[-1])
        prev = float(history["Close"].iloc[-2])
        if prev == 0:
            return None
        change_pct = ((close - prev) / prev) * 100
        return MarketIndexQuote(
            symbol=symbol,
            label=label,
            price=round(close, 2),
            change_pct=round(change_pct, 2),
        )
    except Exception:
        return None
