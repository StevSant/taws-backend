"""Cover for `format_personalized_event_alert` — the watchlist-targeted alert body.

Asserts the two-section shape: the reused market analysis PLUS a personal "why this matters to
you" section, and its deterministic symbol-list fallback when an asset has no impact blurb.

Per `backend/CLAUDE.md`: a minimal targeted test next to the behavior under test.
"""

from datetime import UTC, datetime

from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.infrastructure.telegram import format_event_alert, format_personalized_event_alert


def _event() -> EnrichedEvent:
    return EnrichedEvent(
        id="e1",
        original=NewsEvent(
            title="AAPL jumps on earnings", description="d", content="c", source="s"
        ),
        summary="Apple beat expectations.",
        importance=0.80,
        should_notify=True,
        affected_assets=["AAPL"],
        affected_sectors=["Technology"],
        confidence=0.9,
        reasoning="r",
        suggested_questions=[],
        analyzed_at=datetime.now(UTC),
    )


def test_renders_both_market_and_personal_sections() -> None:
    text = format_personalized_event_alert(
        _event(), ["AAPL"], {"AAPL": "Sube por resultados sólidos."}
    )

    # Market section reused verbatim from the broadcast formatter.
    assert "🚨 ALERTA DE MERCADO" in text
    assert "Apple beat expectations." in text
    # Personal section, in the same Spanish style.
    assert "👤 Por qué te importa" in text
    assert "AAPL" in text
    assert "Sube por resultados sólidos." in text


def test_market_section_is_reused_unchanged() -> None:
    event = _event()
    text = format_personalized_event_alert(event, ["AAPL"], {"AAPL": "Impacto directo."})
    # The whole market body is present as a prefix — personalization is additive, not a rewrite.
    assert text.startswith(format_event_alert(event))


def test_falls_back_to_plain_symbol_list_without_impact_text() -> None:
    text = format_personalized_event_alert(_event(), ["NVDA", "AMD"], {})

    assert "👤 Por qué te importa" in text
    # No impact blurb for either symbol -> the deterministic listing line.
    assert "Afecta a NVDA, AMD en tu watchlist" in text


def test_mixes_blurbs_and_fallback_line_when_some_assets_lack_impact() -> None:
    text = format_personalized_event_alert(
        _event(), ["NVDA", "AMD"], {"NVDA": "Cadena de suministro expuesta."}
    )

    assert "Cadena de suministro expuesta." in text
    # AMD has no blurb, so it drops to the fallback line (NVDA does not).
    assert "Afecta a AMD en tu watchlist" in text


def test_no_matched_symbols_returns_plain_market_alert() -> None:
    event = _event()
    text = format_personalized_event_alert(event, [], {})
    assert text == format_event_alert(event)
