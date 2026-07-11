from datetime import datetime

from pydantic import BaseModel


class TelegramLinkStatusResponse(BaseModel):
    """Response payload for `GET /api/v1/telegram/link` — whether the current user has a
    linked Telegram chat, so the frontend can render "connect" vs. "connected" without
    guessing from a 404."""

    linked: bool
    linked_at: datetime | None
