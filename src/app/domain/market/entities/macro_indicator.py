from enum import StrEnum


class MacroIndicator(StrEnum):
    """A macro-economic indicator the "Contexto de mercado" panel can chart (issue #58).

    Each value maps to a configured FRED series id in the live adapter and to a fixture base
    value in the fallback adapter — so which concrete series backs each indicator stays in
    `Settings`, never hardcoded in the provider.
    """

    RATES = "rates"
    CPI = "cpi"
    GOLD = "gold"
    OIL = "oil"
    TREASURY_10Y = "treasury_10y"
