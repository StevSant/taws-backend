from dataclasses import dataclass


@dataclass(slots=True)
class BriefingCommand:
    """A parsed `/briefing` command from a Telegram webhook update (issue #19)."""

    chat_id: str
