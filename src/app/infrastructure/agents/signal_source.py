from typing import Literal

from pydantic import BaseModel, Field


class SignalSource(BaseModel):
    kind: Literal["signal"] = "signal"
    symbol: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    signal_id: str | None = None
