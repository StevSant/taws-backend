from pydantic import BaseModel, ConfigDict


class InstrumentFundamentalsResponse(BaseModel):
    """Response payload for one instrument's basic fundamentals."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    market_cap: float | None = None
    pe_ratio: float | None = None
    dividend_yield: float | None = None
    sector: str | None = None
