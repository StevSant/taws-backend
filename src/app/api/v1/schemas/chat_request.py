from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/stream`."""

    message: str = Field(..., description="User message to send to the agent.")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id; omit to start a new thread."
    )
    asset_symbol: str | None = Field(
        default=None,
        description=(
            "Optional ticker of a market asset to ground the answer on. Mutually "
            "exclusive with `news_id`; when both are set, `asset_symbol` takes precedence."
        ),
    )
    news_id: str | None = Field(
        default=None,
        description=(
            "Optional id of a news article to ground the answer on. Mutually exclusive "
            "with `asset_symbol`."
        ),
    )
