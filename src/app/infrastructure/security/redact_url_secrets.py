import re

# Query-param names whose values are secrets and must never reach the logs. Matched
# case-insensitively (so `api_token`, `API_KEY`, `apiKey` all hit). httpx bakes the full
# request URL — query string included — into `HTTPStatusError`'s message, so logging a bare
# `str(exc)` from a provider that keys off a `?api_token=...` query param leaks the key.
_SECRET_QUERY_PARAMS = ("api_token", "api_key", "apikey", "token", "key", "secret", "password")
_SECRET_QUERY_PATTERN = re.compile(
    rf"(?i)([?&](?:{'|'.join(_SECRET_QUERY_PARAMS)})=)[^&\s]+"
)


def redact_url_secrets(text: str) -> str:
    """Mask secret query-param values in any string (e.g. an exception message with a URL).

    `redact_url_secrets("...?api_token=abc123&language=en")` ->
    `"...?api_token=REDACTED&language=en"`. Only the value of a known-secret query param is
    replaced; the param name and the rest of the string are left intact so the log line
    still says *which* request failed.
    """
    return _SECRET_QUERY_PATTERN.sub(r"\1REDACTED", text)
