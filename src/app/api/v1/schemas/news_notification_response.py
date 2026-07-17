from typing import Literal

from pydantic import BaseModel


class NewsNotificationResponse(BaseModel):
    """Outcome of asking Sentinel to notify the caller about one news item."""

    status: Literal["sent", "not_relevant"]
    event_title: str
