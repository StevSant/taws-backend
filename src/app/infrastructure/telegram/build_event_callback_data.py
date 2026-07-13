from app.infrastructure.telegram.event_callback_action import EventCallbackAction

# Telegram's hard cap on `callback_data` (https://core.telegram.org/bots/api#inlinekeyboardbutton).
# Exceeding it makes the API reject the whole sendMessage, so the alert would vanish entirely
# rather than merely losing a button.
CALLBACK_DATA_MAX_BYTES = 64

_SEPARATOR = ":"


class CallbackDataTooLongError(ValueError):
    """Raised when an encoded callback token would exceed Telegram's 64-byte limit."""


def build_event_callback_data(
    action: EventCallbackAction, event_id: str, question_index: int | None = None
) -> str:
    """Encode a button's action into Telegram's 64-byte `callback_data` field.

    Shape: `<action>:<event_id>[:<question_index>]` — e.g. `q:6f9a...:0`, `i:6f9a...`.

    Only an id and an index travel in the token, never the payload: a suggested question is a
    full sentence and a news title is longer still, so neither can fit. The handler re-reads
    the event from `EventRepositoryPort.get()` on the way back.

    A uuid4 event id is 36 bytes, leaving comfortable headroom — but this raises rather than
    silently truncating if that ever stops being true, because a truncated token would decode
    to the wrong event (or no event) at tap time, long after anyone is watching.
    """
    parts = [action.value, event_id]
    if question_index is not None:
        parts.append(str(question_index))
    data = _SEPARATOR.join(parts)

    encoded_length = len(data.encode("utf-8"))
    if encoded_length > CALLBACK_DATA_MAX_BYTES:
        raise CallbackDataTooLongError(
            f"callback_data is {encoded_length} bytes, over Telegram's "
            f"{CALLBACK_DATA_MAX_BYTES}-byte limit: {data!r}"
        )
    return data
