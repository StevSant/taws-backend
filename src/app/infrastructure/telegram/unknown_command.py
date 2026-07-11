from dataclasses import dataclass


@dataclass(slots=True)
class UnknownCommand:
    """A Telegram message that looks like a command attempt (starts with `/`) but
    doesn't match any recognized command, or matches one but is missing a required
    argument (e.g. bare `/signal` with no ticker, `/simular` with no text) (issue #19).

    Distinguishing this from `None` (parsing's "nothing to do" result for ordinary,
    non-command chat text) is what lets the webhook router satisfy the "malformed
    commands get a helpful error reply, not a silent failure" acceptance criterion
    without turning every stray message into a reply — see `parse_telegram_command`'s
    docstring for the full decision.
    """

    chat_id: str
    raw_text: str
