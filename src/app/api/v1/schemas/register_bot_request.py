from pydantic import BaseModel, Field


class RegisterBotRequest(BaseModel):
    """Request body for `POST /api/v1/telegram/register-bot`.

    The user pastes the full message they received from BotFather after creating
    their bot. The system extracts the bot token and username from this text.
    """

    botfather_text: str = Field(
        ...,
        description="Full message from BotFather after creating a new bot",
        examples=[
            "Done! Congratulations on your new bot. You will find it at "
            "t.me/MidasTestBot. ... Use this token to access the HTTP API:\n"
            "8683925755:AAEkpC1KdpjlYd07hzsDswXUHZjYSaF1Q2k"
        ],
    )
