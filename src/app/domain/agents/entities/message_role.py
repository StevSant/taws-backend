from enum import StrEnum


class MessageRole(StrEnum):
    """Who authored a chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
