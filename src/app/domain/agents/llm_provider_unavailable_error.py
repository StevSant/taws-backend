class LLMProviderUnavailableError(RuntimeError):
    """Raised by an `LLMProvider` adapter when its backend can't be reached in a way no
    retry can fix — e.g. no API key configured, so the client was never constructed.

    Deliberately distinct from *transient* failures (rate limits, timeouts, malformed or
    unparseable structured output), which adapters raise as ordinary exceptions so callers
    can retry them before degrading. Callers that fall back gracefully — see
    `application/signals/use_cases/generate_signal.py` — catch this to skip the retry loop
    and degrade immediately, while retrying anything else. Subclasses `RuntimeError` so the
    port's existing "raise rather than return a malformed dict" contract (and any broad
    `except RuntimeError` / `except Exception` caller) keeps working unchanged.
    """
