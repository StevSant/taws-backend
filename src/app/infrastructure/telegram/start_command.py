from dataclasses import dataclass


@dataclass(slots=True)
class StartCommand:
    """A parsed `/start <token>` deep-link command from a Telegram webhook update."""

    chat_id: str
    token: str
