from dataclasses import dataclass


@dataclass
class UserBot:
    """A Telegram bot registered by a user, created via BotFather.

    Each user can register at most one bot. The bot is used to:
    - Send notifications (alerts, briefings, scenario matches) to the user's chat
    - Receive messages from the user via webhook and route to the Supervisor graph

    `bot_token` is the HTTP API token from BotFather (e.g. `8683925755:AAE...`).
    `bot_username` is the bot's @username (e.g. `MidasTestBot`).
    `chat_id` is the user's Telegram chat ID with this bot, obtained via `getUpdates`.
    """

    id: str
    user_id: str
    bot_token: str
    bot_username: str
    chat_id: str
