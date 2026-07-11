_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_TRUNCATION_SUFFIX = "…"


def truncate_telegram_text(text: str, limit: int = _TELEGRAM_MAX_MESSAGE_LENGTH) -> str:
    """Truncate `text` to Telegram's `sendMessage` character limit (4096, per
    https://core.telegram.org/bots/api#sendmessage), leaving room for a `…` suffix.

    Every formatter in this package (`format_briefing_reply`, `format_signal_reply`,
    `format_scenario_result_reply`) only wraps HTML tags around SHORT, fixed pieces
    near the start of the message (e.g. a bolded header) — the long, variable-length
    part (summary/narrative/evidence) is always plain, tag-free escaped text placed
    after them. So a plain right-truncation here never risks cutting a `parse_mode`
    tag in half; worst case it cuts mid HTML-entity (e.g. `&amp;` -> `&am`), which
    Telegram's parser tolerates as literal text rather than a parse error.
    """
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX
