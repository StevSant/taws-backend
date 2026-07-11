from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NewsEventResponse(BaseModel):
    """Response payload for a raw `NewsEvent`."""

    model_config = ConfigDict(from_attributes=True)

    title: str
    description: str
    content: str
    source: str
    url: str | None = None
    published_at: datetime | None = None
