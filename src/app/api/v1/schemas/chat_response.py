from pydantic import BaseModel


class ChatResponse(BaseModel):
    """Full assistant reply, for non-streaming callers."""

    thread_id: str
    reply: str
