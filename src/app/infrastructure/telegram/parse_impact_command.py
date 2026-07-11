from app.infrastructure.telegram.impact_command import ImpactCommand

_IMPACT_TOKEN = "/impact"


def parse_impact_command(chat_id: str, text: str) -> ImpactCommand | None:
    """Parse a `/impact <sector>` command out of an already-extracted `(chat_id, text)`
    pair. Returns `None` both when `text` isn't an `/impact` command at all AND when
    it's missing its sector argument — same pattern as `parse_signal_command`."""
    stripped = text.strip()
    first_token, _, rest = stripped.partition(" ")
    if first_token.lower() != _IMPACT_TOKEN:
        return None
    sector = rest.strip()
    if not sector:
        return None
    return ImpactCommand(chat_id=chat_id, sector=sector)