from pydantic import BaseModel, Field


class GetMarketDataArgs(BaseModel):
    """Validated arguments for the `get_market_data` realtime tool.

    `symbol` is required and normalized to upper-case; `days` bounds the returned price
    series window. Extra fields are rejected so a compromised/hallucinated model call
    can't smuggle unexpected parameters through to the backend.
    """

    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=32)
    days: int = Field(default=30, ge=1, le=365)
