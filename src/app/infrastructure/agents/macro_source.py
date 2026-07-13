from typing import Literal

from pydantic import BaseModel, Field


class MacroSource(BaseModel):
    kind: Literal["macro"] = "macro"
    indicator: str = Field(min_length=1)
    value: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    provider: str = Field(min_length=1)
