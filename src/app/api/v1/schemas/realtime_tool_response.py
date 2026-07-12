from typing import Any

from pydantic import BaseModel


class RealtimeToolResponse(BaseModel):
    """Response for `POST /api/v1/chat/realtime/tool`.

    `output` is the tool's JSON-serializable result, relayed by the browser back to the
    model as a `function_call_output`. On a recoverable tool/use-case failure (bad symbol,
    insufficient evidence), `output` carries a structured `{"error": ...}` so the model can
    recover verbally — the endpoint does not 500 on those.
    """

    call_id: str
    output: dict[str, Any]
