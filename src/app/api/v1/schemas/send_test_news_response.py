from pydantic import BaseModel


class SendTestNewsResponse(BaseModel):
    """Result of `POST /api/v1/telegram/send-test-news`.

    The frontend's "Send Test News" button renders `event_title` on success, and the
    `detail` of a 400 (no news event available / no Telegram bot configured) on failure.
    """

    status: str
    event_title: str
