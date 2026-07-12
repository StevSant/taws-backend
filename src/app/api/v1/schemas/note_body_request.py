from pydantic import BaseModel, Field


class NoteBodyRequest(BaseModel):
    """Request payload carrying a note's body, shared by `POST` (create) and `PATCH`
    (update) on `/api/v1/notes` — both only ever set the free-text body."""

    body: str = Field(..., min_length=1, max_length=2000)
