import logging
import sys

from app.core.logging.redact_query_params_filter import RedactQueryParamsFilter


def configure_logging(level: int = logging.INFO) -> None:
    """Configure stdlib logging with a simple, consistent format.

    Minimal on purpose: this is plain logging (per the hackathon's "minimal plain
    logging" decision), not a structured/JSON pipeline.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )

    # Scrub secret-bearing query params from every log line as a safety net (issue #45).
    redactor = RedactQueryParamsFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)

    # httpx/httpcore log the full request URL at INFO ("HTTP Request: GET https://...?apiKey=...").
    # Raise them to WARNING so request-URL lines (which can carry a secret in the query
    # string) never hit stdout in the first place (issue #45).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
