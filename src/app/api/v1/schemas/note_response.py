from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.note_target_response import NoteTargetResponse


class NoteResponse(BaseModel):
    """Response payload for a single note."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    body: str
    target: NoteTargetResponse | None = None
    created_at: datetime
    updated_at: datetime
