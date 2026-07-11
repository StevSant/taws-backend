from dataclasses import dataclass


@dataclass(slots=True)
class ChatMessage:
    """A non-command text message from a Telegram user, to be routed to the agent."""

    chat_id: str
    text: str
