from datetime import date

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
    from_date: date | None = Field(
        default=None,
        description=(
            "Optional start (YYYY-MM-DD) of a chart date window; with `to_date` and "
            "`asset_symbol` it grounds the answer on the asset's news in that period."
        ),
    )
    to_date: date | None = Field(
        default=None,
        description="Optional end (YYYY-MM-DD) of the date window; see `from_date`.",
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
