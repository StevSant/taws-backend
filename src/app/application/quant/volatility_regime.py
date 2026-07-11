from enum import StrEnum


class VolatilityRegime(StrEnum):
    """A coarse bucket for an instrument's recent annualized volatility.

    Cutoffs live as private constants next to `ComputeMarketStats._classify_volatility_regime`
    (`use_cases/compute_market_stats.py`) — generic equity-style annualized-volatility bands,
    a documented T1 simplification (see that use case's docstring) rather than a per-asset-class
    calibrated model.
    """

    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
