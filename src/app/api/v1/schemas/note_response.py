from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoteResponse(BaseModel):
    """Response payload for a single note."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    body: str
    created_at: datetime
    updated_at: datetime
