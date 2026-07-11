from abc import ABC, abstractmethod

from app.domain.sentiment.entities import FearGreedReading


class FearGreedProvider(ABC):
    """Port for the market-wide Fear & Greed Index (issue #21).

    A dedicated port rather than folding into `MacroDataProvider`
    (`domain/market/ports/macro_data_provider.py`): that port's shape is already used
    elsewhere (Scenario context gathering, the Analyst pipeline) keyed on
    rates/CPI/volatility specifically, and Fear & Greed is a distinct concern (crowd
    sentiment, not a FRED/VIX macro figure) with its own adapter (alternative.me, no key
    required) and its own fixture fallback — same "one port, one responsibility"
    rationale as keeping `NewsProvider` separate from `MacroDataProvider`. Adapters:
    `AlternativeMeFearGreedProvider` (live), `FixtureFearGreedProvider` (fallback), and
    `RoutingFearGreedProvider` (prefers live, falls back on any failure) — see
    `infrastructure/sentiment/`.
    """

    @abstractmethod
    async def get_fear_greed_index(self) -> FearGreedReading:
        """Return the current Fear & Greed Index reading."""
        raise NotImplementedError
