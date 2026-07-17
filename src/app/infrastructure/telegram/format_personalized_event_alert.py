import html
from collections.abc import Mapping, Sequence

from app.domain.event_intelligence.entities import EnrichedEvent
from app.infrastructure.telegram.format_event_alert import format_event_alert
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_SEPARATOR = "━━━━━━━━━━━━━━━━━━"


def format_personalized_event_alert(
    event: EnrichedEvent,
    watched_symbols: Sequence[str],
    asset_impacts: Mapping[str, str],
) -> str:
    """Render a watchlist-targeted event alert with a personal "why this matters to you" section.

    Two stacked sections, in the same Spanish HTML style as `format_event_alert`:

    1. The MARKET analysis — reused verbatim from `format_event_alert(event)` (the same
       "how this matters to the market" body a broadcast alert carries). Personalization is
       ADDED after it, never a replacement, so the market read is identical for every user.
    2. A PERSONAL "👤 Por qué te importa" section built from THIS user's matched watchlist
       symbols (`watched_symbols`) plus the shared per-asset impact map (`asset_impacts`,
       asset symbol -> impact blurb, computed once per event and reused across every user
       watching that asset). Each matched symbol that has an impact blurb is rendered with it;
       symbols without one collapse into a deterministic "Afecta a X, Y en tu watchlist" line —
       so the section is always meaningful even when the analyzer produced no impact text.

    Buttons are NOT rendered here (same as `format_event_alert`): the caller keeps building the
    inline keyboard with `build_event_alert_buttons`. Falls back to the plain market alert when
    there are no matched symbols to personalize with.
    """
    market_section = format_event_alert(event)
    if not watched_symbols:
        return market_section

    lines = [market_section, "", _SEPARATOR, "", "<b>👤 Por qué te importa</b>"]

    with_impact: list[str] = []
    without_impact: list[str] = []
    for symbol in watched_symbols:
        blurb = asset_impacts.get(symbol, "")
        if blurb and blurb.strip():
            with_impact.append(symbol)
        else:
            without_impact.append(symbol)

    for symbol in with_impact:
        lines.append("")
        lines.append(f"<b>{html.escape(symbol)}</b>")
        lines.append(html.escape(asset_impacts[symbol].strip()))

    if without_impact:
        lines.append("")
        lines.append(f"Afecta a {html.escape(', '.join(without_impact))} en tu watchlist")

    return truncate_telegram_text("\n".join(lines))
