from dataclasses import dataclass

from app.infrastructure.telegram.event_callback_action import EventCallbackAction


@dataclass(slots=True)
class EventCallback:
    """A tapped inline button on a broadcast news alert, parsed from a `callback_query` update.

    Sits alongside the `/start`, `/briefing`, `/signal`, `/simular`, `/impact` command objects
    as one more thing `parse_telegram_command` can return — but it is the first that does NOT
    come from a `message` update. Telegram delivers button taps as a separate `callback_query`
    update, which the webhook previously dropped on the floor (`extract_message_text_and_chat_id`
    explicitly returns `None` for them).

    `callback_query_id` is what `answerCallbackQuery` needs to stop the client's spinner; it
    must be answered even when we cannot act on the callback.

    `question_index` is only meaningful for `ASK_QUESTION` — it indexes into the event's
    `suggested_questions`, because the question text itself is far too long for the 64-byte
    `callback_data` budget.
    """

    chat_id: str
    callback_query_id: str
    event_id: str
    action: EventCallbackAction
    question_index: int | None = None
