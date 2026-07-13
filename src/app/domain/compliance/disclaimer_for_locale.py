from app.domain.compliance.disclaimer import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.compliance.disclaimer_es import NOT_PERSONALIZED_ADVICE_DISCLAIMER_ES

_DISCLAIMERS_BY_LANGUAGE = {
    "es": NOT_PERSONALIZED_ADVICE_DISCLAIMER_ES,
    "en": NOT_PERSONALIZED_ADVICE_DISCLAIMER,
}


def disclaimer_for_locale(locale: str) -> str:
    """Return the not-personalized-advice disclaimer written in `locale`.

    Matches on the primary language subtag, so `es-MX`/`es-419` resolve to the Spanish text
    rather than silently falling back to English. An unknown language falls back to the
    English constant — a disclaimer in the wrong language is still a disclaimer, so this must
    never raise and never return empty: the text is a structural compliance requirement on
    every alert, not decoration.
    """
    language = locale.split("-", 1)[0].strip().lower()
    return _DISCLAIMERS_BY_LANGUAGE.get(language, NOT_PERSONALIZED_ADVICE_DISCLAIMER)
