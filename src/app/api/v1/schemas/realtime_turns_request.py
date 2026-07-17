from pydantic import BaseModel, Field

from app.api.v1.schemas.realtime_turn import RealtimeTurn


class RealtimeTurnsRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/realtime/turns` (issue #6).

    Appends completed voice turns to the `conversations` row bound to the realtime session
    (the `conversation_id` returned by `POST /chat/realtime/session`), via the SAME
    `ConversationRepository` the text chat persists through — so voice threads survive a
    refresh like text threads. The caller must own `conversation_id`."""

    conversation_id: str = Field(..., description="The realtime session's bound conversation.")
    turns: list[RealtimeTurn] = Field(..., description="Completed user/assistant turns, in order.")
