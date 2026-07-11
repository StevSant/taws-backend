import html

from app.domain.event_intelligence.entities import EnrichedEvent
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text


def format_event_alert(event: EnrichedEvent) -> str:
    """Render a Telegram-friendly (HTML `parse_mode`) alert for an important
    news event detected by the Sentinel pipeline.

    Includes the event title, summary, affected sectors/assets, and suggested
    questions. Truncated to Telegram's 4096-char limit if needed.
    """
    lines = [
        "<b>🚨 Important News Event</b>",
        "",
        f"<b>{html.escape(event.original.title)}</b>",
        "",
        html.escape(event.summary) if event.summary else "",
        "",
    ]

    if event.affected_sectors:
        sectors = ", ".join(html.escape(s) for s in event.affected_sectors)
        lines.append(f"<b>Sectors:</b> {sectors}")

    if event.affected_assets:
        assets = ", ".join(html.escape(a) for a in event.affected_assets)
        lines.append(f"<b>Assets:</b> {assets}")

    lines.append(f"<b>Confidence:</b> {event.confidence:.0%}")

    if event.suggested_questions:
        lines.append("")
        lines.append("<b>Ask me:</b>")
        for q in event.suggested_questions:
            lines.append(f"• {html.escape(q)}")

    return truncate_telegram_text("\n".join(lines))