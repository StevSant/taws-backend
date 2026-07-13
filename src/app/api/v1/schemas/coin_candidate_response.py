from pydantic import BaseModel, ConfigDict


class CoinCandidateResponse(BaseModel):
    """Response payload for one `GET /api/v1/instruments/search` hit."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    name: str
    market_cap_rank: int | None
    thumb: str
