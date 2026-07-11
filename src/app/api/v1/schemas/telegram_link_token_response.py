from datetime import datetime

from pydantic import BaseModel


class TelegramLinkTokenResponse(BaseModel):
    """Response payload for `POST /api/v1/telegram/link-token`."""

    token: str
    deep_link_url: str | None
    expires_at: datetime
