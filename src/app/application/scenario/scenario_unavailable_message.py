_MESSAGES: dict[str, str] = {
    "es": (
        "No pudimos generar el análisis del escenario en este momento. "
        "Volvé a intentarlo en unos minutos."
    ),
    "en": (
        "We couldn't generate the scenario analysis right now. Please try again in a few minutes."
    ),
}
_DEFAULT_LOCALE = "en"


def scenario_unavailable_message(locale: str) -> str:
    """Return an honest, user-facing "analysis unavailable" message in `locale`.

    Surfaced by `POST /api/v1/scenarios/generate` when synthesis raises
    `ScenarioSynthesisUnavailableError` (issue #64) — the UI shows this instead of a
    fabricated zero-confidence result. Matches on the primary language subtag (e.g.
    `es-MX` -> `es`) and falls back to English for any locale we don't have copy for.
    """
    primary_subtag = locale.split("-", 1)[0].lower() if locale else _DEFAULT_LOCALE
    return _MESSAGES.get(primary_subtag, _MESSAGES[_DEFAULT_LOCALE])
