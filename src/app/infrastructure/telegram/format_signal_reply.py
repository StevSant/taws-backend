import html

from app.domain.signals.entities import Signal
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_MAX_EVIDENCE_ITEMS = 3


def format_signal_reply(signal: Signal) -> str:
    impact_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(
        signal.impact_class.value, "⚪"
    )
    impact_label = {"bullish": "Alcista", "bearish": "Bajista", "neutral": "Neutral"}.get(
        signal.impact_class.value, signal.impact_class.value.capitalize()
    )
    header = f"<b>{html.escape(signal.instrument_symbol)}</b> — {impact_emoji} {impact_label}"
    evidence_lines = "\n".join(
        f"• {html.escape(item.source)} ({item.published_at.date().isoformat()})"
        for item in signal.evidence[:_MAX_EVIDENCE_ITEMS]
    )
    disclaimer = html.escape(signal.disclaimer)

    body_parts = [header]
    body_parts.append(f"🎯 <b>Confianza</b>\n{signal.confidence:.0%}")
    if evidence_lines:
        body_parts.append(f"📊 <b>Evidencia</b>\n{evidence_lines}")
    body_parts.append(f"\n━━━━━━━━━━━━━━━━━━\n{disclaimer}")
    return truncate_telegram_text("\n\n".join(body_parts))
