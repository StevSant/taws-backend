from pydantic import BaseModel, Field


class RealtimeSessionResponse(BaseModel):
    """Response for `POST /api/v1/chat/realtime/session`.

    Carries ONLY the ephemeral `ek_*` client secret the browser uses to open its own
    WebRTC connection to OpenAI — the real Realtime API key never appears here. `tools`
    echoes the server-authored tool schema the session was minted with, so the frontend
    knows exactly which function calls the backend will honor.
    """

    client_secret: str = Field(description="Ephemeral ek_* secret for browser WebRTC.")
    model: str
    expires_at: int = Field(description="Unix epoch seconds when the secret expires.")
    tools: list[dict] = Field(default_factory=list)
    conversation_id: str = Field(
        default="",
        description=(
            "Real conversations row bound to this voice session; the browser persists "
            "completed voice turns to it via POST /chat/realtime/turns so a refresh rehydrates "
            "them."
        ),
    )
