from abc import ABC, abstractmethod

from app.domain.market.entities import MacroObservation, VolatilityRegime


class MacroDataProvider(ABC):
    """Port for macro-economic state: interest rates, CPI (FRED), and the VIX-derived
    volatility regime.

    One port, multiple related concerns — rates/CPI/VIX are all "macro state" consumed
    together by the Analyst/Advisor pipelines and the Scenario engine (issue #12), so they
    don't warrant three separate ports. Adapters: FRED (rates + CPI, requires `FRED_API_KEY`)
    combined with a `yfinance`-backed `^VIX` lookup (volatility regime, no key required), and a
    deterministic fixture fallback — see `infrastructure/macro/`.
    """

    @abstractmethod
    async def get_rates(self) -> MacroObservation:
        """Return the latest observation for the primary policy-rate FRED series."""
        raise NotImplementedError

    @abstractmethod
    async def get_cpi(self) -> MacroObservation:
        """Return the latest observation for the headline CPI FRED series."""
        raise NotImplementedError

    @abstractmethod
    async def get_volatility_regime(self) -> VolatilityRegime:
        """Return the current VIX level and its derived `VolatilityLevel` regime bucket."""
        raise NotImplementedError
