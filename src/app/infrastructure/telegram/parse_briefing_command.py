from app.infrastructure.telegram.briefing_command import BriefingCommand

_BRIEFING_TOKEN = "/briefing"


def parse_briefing_command(chat_id: str, text: str) -> BriefingCommand | None:
    """Parse a `/briefing` command out of an already-extracted `(chat_id, text)` pair
    (see `extract_message_text_and_chat_id`). Takes no arguments — any trailing text is
    ignored. Returns `None` if `text` isn't a `/briefing` command at all (a different
    command, or ordinary chat text)."""
    first_token = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    if first_token.lower() != _BRIEFING_TOKEN:
        return None
    return BriefingCommand(chat_id=chat_id)
