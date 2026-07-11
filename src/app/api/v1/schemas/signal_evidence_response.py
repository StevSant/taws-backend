from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SignalEvidenceResponse(BaseModel):
    """Response payload for one evidence entry backing a `Signal`."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    published_at: datetime
    url: str | None = None
    detail: str | None = None
