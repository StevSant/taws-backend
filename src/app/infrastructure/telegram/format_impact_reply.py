import html

from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text


def format_impact_reply(sector: str, analysis: str) -> str:
    text = (
        f"🏛️ <b>Impacto en {html.escape(sector)}</b>"
        f"\n\n━━━━━━━━━━━━━━━━━━"
        f"\n\n{html.escape(analysis)}"
    )
    return truncate_telegram_text(text)
