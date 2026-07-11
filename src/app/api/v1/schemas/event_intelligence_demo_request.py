from pydantic import BaseModel, Field


class EventIntelligenceDemoRequest(BaseModel):
    """Request payload for `POST /api/v1/event-intelligence/demo`.

    Allows manual injection of a news event into the Event Intelligence pipeline.
    When `telegram_chat_id` is provided and the analyzed event has `should_notify`
    set, a notification is sent to that Telegram chat. Set `force_notify` to
    bypass the `should_notify` check for testing.
    """

    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)
    content: str = Field(min_length=1, max_length=10000)
    source: str = Field(default="manual", max_length=100)
    telegram_chat_id: str | None = Field(default=None, max_length=100)
    force_notify: bool = Field(default=False)
