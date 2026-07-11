from typing import Any


def extract_message_text_and_chat_id(update_payload: dict[str, Any]) -> tuple[str, str] | None:
    """Pull `(chat_id, text)` out of a raw Telegram webhook `Update` payload
    (https://core.telegram.org/bots/api#update), or `None` if this update isn't a plain
    text message (edited messages, callback queries, non-text messages, ...).

    Shared shape-checking helper for every command parser except `parse_start_command`
    (which predates this helper and keeps its own inline copy — left untouched to avoid
    any risk to the already-merged, working issue #14 flow).
    """
    message = update_payload.get("message")
    if not isinstance(message, dict):
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict) or "id" not in chat:
        return None

    return str(chat["id"]), text
