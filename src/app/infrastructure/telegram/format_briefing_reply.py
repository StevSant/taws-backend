import html

from app.domain.briefing.entities import Briefing
from app.domain.watchlist.entities import Watchlist
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text


def format_briefing_reply(briefing: Briefing, watchlist: Watchlist, frontend_base_url: str) -> str:
    """Render a Telegram-friendly (HTML `parse_mode`) reply for `/briefing` (issue #19):
    the watchlist name as a bold header, the briefing's executive summary (`summary`,
    per `Briefing`'s docstring — issue #16's richer document reuses this field for
    exactly that), a link back to the full document in the app, and the compliance
    disclaimer. Truncated to Telegram's 4096-char limit if needed.
    """
    header = f"<b>Latest briefing — {html.escape(watchlist.name)}</b>"
    summary = html.escape(briefing.summary)
    link = f"{frontend_base_url.rstrip('/')}/watchlists/{watchlist.id}?briefing={briefing.id}"
    disclaimer = html.escape(briefing.disclaimer)
    body = f"{header}\n\n{summary}\n\nFull briefing: {link}\n\n{disclaimer}"
    return truncate_telegram_text(body)
