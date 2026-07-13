from app.domain.signals.entities import Signal
from app.domain.signals.entities.impact_class import ImpactClass

_FALLBACK_SOURCE = {"es": "la actividad reciente del mercado", "en": "recent market activity"}

_HINT_TEMPLATES = {
    "es": {
        ImpactClass.POSITIVE: (
            "{symbol} muestra una señal de impacto positivo (confianza {confidence:.0%}), "
            "según {source}. Vale la pena revisarlo — no es una instrucción de compra o venta."
        ),
        ImpactClass.NEGATIVE: (
            "{symbol} muestra una señal de impacto negativo (confianza {confidence:.0%}), "
            "según {source}. Vale la pena revisarlo — no es una instrucción de compra o venta."
        ),
        ImpactClass.UNCERTAIN: (
            "{symbol} muestra una señal de impacto incierto (confianza {confidence:.0%}), "
            "según {source}. Vale la pena revisarlo — no es una instrucción de compra o venta."
        ),
    },
    "en": {
        ImpactClass.POSITIVE: (
            "{symbol} shows a positive impact signal (confidence {confidence:.0%}), based on "
            "{source}. Worth reviewing — not a trade instruction."
        ),
        ImpactClass.NEGATIVE: (
            "{symbol} shows a negative impact signal (confidence {confidence:.0%}), based on "
            "{source}. Worth reviewing — not a trade instruction."
        ),
        ImpactClass.UNCERTAIN: (
            "{symbol} shows an uncertain impact signal (confidence {confidence:.0%}), based on "
            "{source}. Worth reviewing — not a trade instruction."
        ),
    },
}


def derive_consequence_hint(signal: Signal, locale: str) -> str:
    """Short, non-committal hint derived strictly from the signal's own evidence, in `locale`.

    NOT a call to the Consequence Chain agent (issue #8) — that agent is optional/nice-to-have
    and not hard-depended on here. Never invents facts and never phrases anything as a trade
    instruction.

    Templated rather than LLM-generated, and therefore hardcoded per language: this string is
    the body of a push notification, so it must be cheap, instant, and incapable of drifting
    into a recommendation. It previously existed only in English, which is why Spanish users
    received Spanish UI and English Telegram alerts. An unknown language falls back to English.

    `ImpactClass.NEUTRAL` has no template on purpose — `RunWatchdogScan` filters neutral signals
    out before composing an alert, so reaching here with one is a bug, not a case to paper over;
    `.get` on the inner dict would silently emit a blank hint instead. Hence the explicit
    lookup and `KeyError`.
    """
    language = locale.split("-", 1)[0].strip().lower()
    templates = _HINT_TEMPLATES.get(language, _HINT_TEMPLATES["en"])
    lead_source = (
        signal.evidence[0].source
        if signal.evidence
        else _FALLBACK_SOURCE.get(language, _FALLBACK_SOURCE["en"])
    )
    return templates[signal.impact_class].format(
        symbol=signal.instrument_symbol,
        confidence=signal.confidence,
        source=lead_source,
    )
