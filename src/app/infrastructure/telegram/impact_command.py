from dataclasses import dataclass


@dataclass(slots=True)
class ImpactCommand:
    """A parsed `/impact <sector>` command from a Telegram webhook update.

    `sector` is the market sector or asset the user wants to know the
    impact of the latest important event on.
    """

    chat_id: str
    sector: str
