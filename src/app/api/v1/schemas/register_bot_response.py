from pydantic import BaseModel


class RegisterBotResponse(BaseModel):
    """Response body for `POST /api/v1/telegram/register-bot`."""

    bot_id: str
    bot_username: str
    chat_id: str
    status: str = "ok"
