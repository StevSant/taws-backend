def transcription_language(locale: str) -> str:
    """Reduce a BCP-47-ish locale to the ISO-639-1 code the Realtime transcriber expects.

    The Realtime session's `audio.input.transcription.language` takes a bare language code
    (`es`, `en`) — handing it a full locale like `es-MX` is not accepted. Everything in this
    codebase stores the richer tag (`Settings.default_locale` documents `"es-MX"` as valid, and
    a user's `preferred_locale` is free text), so the tag has to be narrowed at this boundary.

    Previously this was the hardcoded literal `"es"` in `OpenAIRealtimeSessionProvider`, which
    mis-transcribed English speakers' audio as Spanish; the WS transport set no transcription
    language at all.
    """
    return locale.split("-", 1)[0].strip().lower()
