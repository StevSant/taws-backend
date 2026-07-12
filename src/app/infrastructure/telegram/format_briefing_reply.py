import html

from app.domain.briefing.entities import Briefing
from app.domain.watchlist.entities import Watchlist
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text


def format_briefing_reply(briefing: Briefing, watchlist: Watchlist, frontend_base_url: str) -> str:
    header = f"📋 <b>Briefing — {html.escape(watchlist.name)}</b>"
    summary = html.escape(briefing.summary)
    link = f"{frontend_base_url.rstrip('/')}/watchlists/{watchlist.id}?briefing={briefing.id}"
    disclaimer = html.escape(briefing.disclaimer)
    body = (
        f"{header}"
        f"\n\n━━━━━━━━━━━━━━━━━━"
        f"\n\n<b>📌 Summary</b>"
        f"\n{summary}"
        f"\n\n━━━━━━━━━━━━━━━━━━"
        f"\n\n🔗 <a href='{link}'>View full briefing</a>"
        f"\n\n{disclaimer}"
    )
    return truncate_telegram_text(body)
