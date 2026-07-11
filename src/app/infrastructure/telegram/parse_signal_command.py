from app.infrastructure.telegram.signal_command import SignalCommand

_SIGNAL_TOKEN = "/signal"


def parse_signal_command(chat_id: str, text: str) -> SignalCommand | None:
    """Parse a `/signal <TICKER>` command out of an already-extracted `(chat_id, text)`
    pair. Returns `None` both when `text` isn't a `/signal` command at all AND when it
    is one but is missing its ticker argument (e.g. bare `/signal`) — the caller
    (`parse_telegram_command`) treats both the same way: try the next parser, and if
    nothing matches but the text still starts with `/`, report it as `UnknownCommand`
    rather than silently dropping a malformed `/signal`."""
    parts = text.strip().split(maxsplit=2)
    if not parts or parts[0].lower() != _SIGNAL_TOKEN:
        return None
    if len(parts) < 2 or not parts[1].strip():
        return None
    return SignalCommand(chat_id=chat_id, ticker=parts[1].strip())
