from typing import Any

from pydantic import BaseModel, Field


class RealtimeToolRequest(BaseModel):
    """Request for `POST /api/v1/chat/realtime/tool` — a relayed model function call.

    The browser forwards a function call the voice model emitted over its data channel.
    `name` is validated against the server allowlist and `arguments` against that tool's
    Pydantic schema before anything runs. The acting user is taken from the JWT, NEVER
    from `arguments`.
    """

    call_id: str = Field(description="OpenAI function-call id, echoed back in the output.")
    name: str = Field(description="Tool name; must be in the server allowlist.")
    arguments: dict[str, Any] = Field(default_factory=dict)
