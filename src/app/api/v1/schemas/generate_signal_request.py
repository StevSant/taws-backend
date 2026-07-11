from pydantic import BaseModel, Field


class GenerateSignalRequest(BaseModel):
    """Request payload for `POST /api/v1/signals/generate`."""

    instrument_symbol: str = Field(..., min_length=1, max_length=20)
