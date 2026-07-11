import html

from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text


def format_impact_reply(sector: str, analysis: str) -> str:
    """Render a Telegram-friendly (HTML `parse_mode`) reply for `/impact <sector>`.

    Shows the sector and the impact analysis text. Truncated to Telegram's
    4096-char limit if needed.
    """
    text = (
        f"<b>Impact on {html.escape(sector)}</b>\n\n"
        f"{html.escape(analysis)}"
    )
    return truncate_telegram_text(text)