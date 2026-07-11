from dataclasses import dataclass


@dataclass(slots=True)
class SignalCommand:
    """A parsed `/signal <TICKER>` command from a Telegram webhook update (issue #19).

    `ticker` is the raw, as-typed token — case/whitespace as the user sent it.
    Validation against the curated `InstrumentUniverse` happens downstream in
    `SignalCommandHandler`, not at parse time (parsing only checks *shape*, not
    business validity — same split `parse_start_command` draws between "is this
    structurally a `/start <token>` message" and "is `<token>` actually valid").
    """

    chat_id: str
    ticker: str
