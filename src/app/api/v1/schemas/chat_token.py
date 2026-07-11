from pydantic import BaseModel


class ChatToken(BaseModel):
    """A single streamed token of an assistant reply (documentation model for the SSE payload)."""

    token: str
