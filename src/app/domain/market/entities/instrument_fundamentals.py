from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentFundamentals:
    """Basic company/instrument fundamentals (yfinance-sourced).

    Fields are deliberately few and all optional (besides `symbol`): not every instrument in the
    curated universe is an equity with a full fundamentals profile (e.g. FOREX/COMMODITY have
    none of these), so a missing field is `None` rather than a fabricated value.
    """

    symbol: str
    market_cap: float | None
    pe_ratio: float | None
    dividend_yield: float | None
    sector: str | None
