import html

from app.domain.event_intelligence.entities import EnrichedEvent
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_SEPARATOR = "\n━━━━━━━━━━━━━━━━━━\n"


def format_event_alert(event: EnrichedEvent) -> str:
    lines = [
        "<b>🚨 ALERTA DE MERCADO</b>",
        "",
        f"🏛️ <b>{html.escape(event.original.title)}</b>",
        _SEPARATOR.strip(),
    ]

    if event.summary:
        lines.append("<b>📌 Resumen</b>")
        lines.append(html.escape(event.summary))

    if event.affected_sectors:
        lines.append("")
        lines.append("<b>📈 Impacto en el Mercado</b>")
        for sector in event.affected_sectors:
            lines.append(f"• {html.escape(sector)}")

    if event.affected_assets:
        lines.append("")
        lines.append("<b>💰 Activos Afectados</b>")
        for asset in event.affected_assets:
            lines.append(f"• {html.escape(asset)}")

    lines.append("")
    lines.append("<b>🎯 Confianza del Análisis</b>")
    lines.append(f"{event.confidence:.0%}")

    # `suggested_questions` used to be listed here as inert bullet text. They are now rendered
    # as tappable inline buttons instead (`build_event_alert_buttons`), which route straight
    # into the conversational agent — so repeating them in the body would just be noise above
    # the very buttons that act on them.
    return truncate_telegram_text("\n".join(lines))
