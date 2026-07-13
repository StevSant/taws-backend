from typing import Literal

from pydantic import BaseModel, Field


class QuantSource(BaseModel):
    kind: Literal["quant"] = "quant"
    metric: str = Field(min_length=1)
    value: str = Field(min_length=1)
    as_of: str | None = None
    window: str | None = None
