from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NewsSource(BaseModel):
    kind: Literal["news"] = "news"
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: datetime
