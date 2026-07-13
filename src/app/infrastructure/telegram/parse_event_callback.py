from typing import Any

from app.infrastructure.telegram.event_callback import EventCallback
from app.infrastructure.telegram.event_callback_action import EventCallbackAction


def parse_event_callback(update_payload: dict[str, Any]) -> EventCallback | None:
    """Parse a Telegram `callback_query` update (an inline-button tap) into an `EventCallback`.

    Returns `None` for anything that isn't a well-formed button tap we recognize — a plain
    message, a callback with no data, or a token we didn't mint. Same shape-checking contract as
    `extract_message_text_and_chat_id`: validate defensively and decline, never raise, since the
    payload is attacker-influenced (anyone can send our bot a crafted update-shaped body if the
    webhook secret ever leaks, and Telegram itself adds new update types over time).

    Expects the token minted by `build_event_callback_data`:
    `<action>:<event_id>[:<question_index>]`.
    """
    callback = update_payload.get("callback_query")
    if not isinstance(callback, dict):
        return None

    callback_id = callback.get("id")
    data = callback.get("data")
    if not isinstance(callback_id, str) or not isinstance(data, str):
        return None

    message = callback.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or "id" not in chat:
        return None

    parts = data.split(":")
    if len(parts) < 2:
        return None

    try:
        action = EventCallbackAction(parts[0])
    except ValueError:
        # A prefix this bot never mints — ignore rather than guess.
        return None

    event_id = parts[1]
    if not event_id:
        return None

    question_index: int | None = None
    if action is EventCallbackAction.ASK_QUESTION:
        if len(parts) < 3:
            return None
        try:
            question_index = int(parts[2])
        except ValueError:
            return None
        if question_index < 0:
            return None

    return EventCallback(
        chat_id=str(chat["id"]),
        callback_query_id=callback_id,
        event_id=event_id,
        action=action,
        question_index=question_index,
    )
