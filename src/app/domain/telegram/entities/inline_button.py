from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InlineButton:
    """One tappable button attached under a Telegram message.

    Pure domain: a `text` label plus exactly one action. `TelegramBotClient` is what turns this
    into the vendor's `InlineKeyboardButton`/`InlineKeyboardMarkup`, so `python-telegram-bot`
    types stay confined to that adapter (see `CLAUDE.md`'s hexagonal rule).

    Exactly one of `url` / `callback_data` must be set — Telegram rejects a button with both,
    and renders one with neither as inert:

    - `url` opens a link (the "Ver en TAWS" deep link back into the web app). Needs no
      server-side handling at all.
    - `callback_data` fires a `callback_query` update back at our webhook when tapped. Telegram
      caps it at **64 bytes**, so it carries an opaque id-and-index token (see
      `build_event_callback_data`), never the payload itself.
    """

    text: str
    url: str | None = None
    callback_data: str | None = None
