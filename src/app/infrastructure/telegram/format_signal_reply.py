import html

from app.domain.signals.entities import Signal
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_MAX_EVIDENCE_ITEMS = 3


def format_signal_reply(signal: Signal) -> str:
    """Render a Telegram-friendly (HTML `parse_mode`) reply for `/signal <TICKER>`
    (issue #19): the bolded ticker, impact class, confidence, up to
    `_MAX_EVIDENCE_ITEMS` evidence sources, and the compliance disclaimer. Truncated to
    Telegram's 4096-char limit if needed.
    """
    header = (
        f"<b>{html.escape(signal.instrument_symbol)}</b> — "
        f"{signal.impact_class.value.capitalize()} "
        f"(confidence {signal.confidence:.0%})"
    )
    evidence_lines = "\n".join(
        f"• {html.escape(item.source)} ({item.published_at.date().isoformat()})"
        for item in signal.evidence[:_MAX_EVIDENCE_ITEMS]
    )
    disclaimer = html.escape(signal.disclaimer)
    body_parts = [header]
    if evidence_lines:
        body_parts.append(evidence_lines)
    body_parts.append(disclaimer)
    return truncate_telegram_text("\n\n".join(body_parts))
