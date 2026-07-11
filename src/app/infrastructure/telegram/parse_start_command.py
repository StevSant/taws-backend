from typing import Any

from app.infrastructure.telegram.start_command import StartCommand

_START_PREFIX = "/start "


def parse_start_command(update_payload: dict[str, Any]) -> StartCommand | None:
    """Extract a `/start <token>` deep-link command from a raw Telegram webhook `Update`
    payload (https://core.telegram.org/bots/api#update).

    Pure dict parsing — no `telegram.Bot` instance required — so it's directly testable
    against a synthetic payload (see the module's usage in `api/v1/routers/telegram.py`).
    Returns `None` for anything that isn't a `/start` text message: Telegram webhooks
    deliver many other update kinds (edited messages, callback queries, chat member
    updates, ...) that this integration deliberately ignores.

    When `/start` is sent without a token, the token is an empty string — the router
    handles this as a welcome message instead of a linking attempt.
    """
    message = update_payload.get("message")
    if not isinstance(message, dict):
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip().startswith("/start"):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict) or "id" not in chat:
        return None

    token = text.strip()[len("/start"):].strip()
    return StartCommand(chat_id=str(chat["id"]), token=token)
