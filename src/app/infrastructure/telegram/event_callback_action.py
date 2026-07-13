from enum import StrEnum


class EventCallbackAction(StrEnum):
    """What a tapped inline button on a broadcast news alert is asking for.

    The values are the literal prefixes encoded into Telegram's `callback_data`, so they are
    deliberately one character: the field is capped at 64 bytes and a uuid event id already
    eats 36 of them.
    """

    ASK_QUESTION = "q"
    ANALYZE_IMPACT = "i"
