from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_TELEGRAM_MAX_CAPTION_LENGTH = 1024


def truncate_telegram_caption(text: str) -> str:
    """Truncate `text` to Telegram's `sendPhoto` caption limit (1024, per
    https://core.telegram.org/bots/api#sendphoto), leaving room for a `…` suffix.

    A photo caption's cap (1024) is a quarter of a message's (4096), so the chart handler
    can't reuse `truncate_telegram_text`'s default. Thin wrapper reusing that function's
    right-truncation with the tighter limit — chart captions are a short title + source,
    so this only ever trims a pathologically long title."""
    return truncate_telegram_text(text, _TELEGRAM_MAX_CAPTION_LENGTH)
