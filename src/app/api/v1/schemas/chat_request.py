from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/stream`."""

    message: str = Field(..., description="User message to send to the agent.")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id; omit to start a new thread."
    )
    # BCP-47-ish locale tag (e.g. "en", "es", "es-MX") the agent must answer in — same bounds
    # as the signal/briefing/scenario request schemas. Omit to fall back to the authenticated
    # user's `preferred_locale`, then to `Settings.default_locale` (issue #67).
    locale: str | None = Field(
        default=None,
        min_length=2,
        max_length=35,
        description="Locale the agent should answer in; omit to use the user's preference.",
    )
