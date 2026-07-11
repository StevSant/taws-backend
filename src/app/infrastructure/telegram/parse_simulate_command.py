from app.infrastructure.telegram.simulate_command import SimulateCommand

_SIMULATE_TOKEN = "/simular"


def parse_simulate_command(chat_id: str, text: str) -> SimulateCommand | None:
    """Parse a `/simular <text>` command out of an already-extracted `(chat_id, text)`
    pair. Everything after the first whitespace-separated token is taken verbatim as
    the free-form scenario description (unlike `/signal`, which expects a single-token
    ticker). Returns `None` both when `text` isn't a `/simular` command at all AND when
    it's missing its free-text argument — see `parse_signal_command`'s docstring for
    why both cases return `None` here."""
    stripped = text.strip()
    first_token, _, rest = stripped.partition(" ")
    if first_token.lower() != _SIMULATE_TOKEN:
        return None
    free_text = rest.strip()
    if not free_text:
        return None
    return SimulateCommand(chat_id=chat_id, text=free_text)
