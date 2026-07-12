import logging
import re

# Query-param names whose values must never reach the logs (case-insensitive). A
# security constant, not deployment config: this is the fixed set of secret-bearing
# param names to scrub, independent of any URL/key/threshold in `Settings`.
_SENSITIVE_QUERY_PARAM_RE = re.compile(r"(?i)([?&](?:apikey|api_key|token)=)[^&\s]+")
_REDACTION = r"\1[REDACTED]"


class RedactQueryParamsFilter(logging.Filter):
    """Logging filter that scrubs sensitive query-param values from a record's message.

    Defense-in-depth safety net (issue #45): even if some library logs a full request
    URL carrying a secret in the query string (e.g. `?apiKey=...`), the value is
    replaced with `[REDACTED]` before the line reaches stdout. Attached to the root
    handler in `configure_logging`, so it covers every logger, not just ours.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _SENSITIVE_QUERY_PARAM_RE.sub(_REDACTION, message)
        if redacted != message:
            # Collapse to the already-rendered, redacted string and drop args so the
            # handler doesn't re-interpolate the original (unredacted) values.
            record.msg = redacted
            record.args = None
        return True
