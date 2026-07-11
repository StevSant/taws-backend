from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MacroObservationResponse(BaseModel):
    """Response payload for a single FRED macro series' latest observation."""

    model_config = ConfigDict(from_attributes=True)

    series_id: str
    value: float
    as_of: datetime
