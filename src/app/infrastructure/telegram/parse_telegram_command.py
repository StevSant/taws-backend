from typing import Any

from app.infrastructure.telegram.extract_message_text_and_chat_id import (
    extract_message_text_and_chat_id,
)
from app.infrastructure.telegram.parse_briefing_command import parse_briefing_command
from app.infrastructure.telegram.parse_chat_message import parse_chat_message
from app.infrastructure.telegram.parse_event_callback import parse_event_callback
from app.infrastructure.telegram.parse_impact_command import parse_impact_command
from app.infrastructure.telegram.parse_signal_command import parse_signal_command
from app.infrastructure.telegram.parse_simulate_command import parse_simulate_command
from app.infrastructure.telegram.parse_start_command import parse_start_command
from app.infrastructure.telegram.telegram_command import TelegramCommand
from app.infrastructure.telegram.unknown_command import UnknownCommand


def parse_telegram_command(update_payload: dict[str, Any]) -> TelegramCommand | None:
    """Parse a raw Telegram webhook `Update` payload into a typed `TelegramCommand`
    (issue #19), or `None` if there's nothing for this webhook to act on.

    Tries each known command in turn — `/start <token>` (issue #14, unchanged), then
    `/briefing`, `/signal <TICKER>`, `/simular <text>` (issue #19) — and returns the
    first match. This is the single dispatch point the router (`api/v1/routers/
    telegram.py`) uses instead of an inline if/elif chain; each individual
    `parse_*_command` stays a small, independently testable pure function.

    Three-way result, not two-way:
    - A typed command object: recognized and well-formed.
    - `ChatMessage`: ordinary chat text (not a command) — routed to the conversational
      agent instead of being silently ignored.
    - `UnknownCommand`: text that LOOKS like a command attempt (starts with `/`) but
      matched nothing above — either a command this bot doesn't support, or a known
      command missing a required argument (`parse_signal_command`/
      `parse_simulate_command` return `None` for that case too, so it falls through to
      here). This is what lets malformed/unknown commands get a helpful reply instead
      of a silent failure, per issue #19's acceptance criteria, without spamming a
      reply to unrelated chat text.
    """
    # Checked first, and separately from everything below: a tapped inline button arrives as a
    # `callback_query` update, not a `message`, so `extract_message_text_and_chat_id` returns
    # `None` for it and every text parser below is structurally incapable of seeing it.
    event_callback = parse_event_callback(update_payload)
    if event_callback is not None:
        return event_callback

    start = parse_start_command(update_payload)
    if start is not None:
        return start

    extracted = extract_message_text_and_chat_id(update_payload)
    if extracted is None:
        return None
    chat_id, text = extracted

    briefing = parse_briefing_command(chat_id, text)
    if briefing is not None:
        return briefing

    signal = parse_signal_command(chat_id, text)
    if signal is not None:
        return signal

    simulate = parse_simulate_command(chat_id, text)
    if simulate is not None:
        return simulate

    impact = parse_impact_command(chat_id, text)
    if impact is not None:
        return impact

    if text.strip().startswith("/"):
        return UnknownCommand(chat_id=chat_id, raw_text=text.strip())

    chat_msg = parse_chat_message(chat_id, text)
    if chat_msg is not None:
        return chat_msg

    return None
