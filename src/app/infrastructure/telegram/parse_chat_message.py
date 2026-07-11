from app.infrastructure.telegram.chat_message import ChatMessage


def parse_chat_message(chat_id: str, text: str) -> ChatMessage | None:
    """Return a `ChatMessage` for any non-command text, or `None` if the text looks
    like a command (starts with `/`).

    This is the last parser in the chain — called only after all known commands have
    been tried and none matched. Non-command text is routed to the conversational agent.
    """
    if text.strip().startswith("/"):
        return None
    return ChatMessage(chat_id=chat_id, text=text)
