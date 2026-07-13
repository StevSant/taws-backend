import re
from html import unescape
from typing import Any

# Feed descriptions are full HTML blobs on some outlets (Yahoo Finance wraps the excerpt in
# `<p>` + a trailing tracking `<img>`); cap the plain-text result so one verbose feed can't
# push a wall of text into the news-detail summary. Same payload-bounding rationale as
# `compute_market_stats._MAX_UNUSUAL_MOVES`.
_MAX_SUMMARY_CHARS = 600
_ELLIPSIS = "…"

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def extract_rss_summary(entry: Any) -> str:
    """Best-effort plain-text summary from a feedparser entry, or `""` when the feed has none.

    Previously `RssNewsProvider` read `entry["summary"]` and nothing else, so every entry whose
    outlet puts the excerpt somewhere else — Yahoo Finance's `content`, an Atom `subtitle` — was
    persisted with an empty summary, and the news-detail page's `@if (news.summary)` section
    silently collapsed (issue #57). This walks the fields in descending order of how likely they
    are to hold the article's own excerpt, and strips the markup they arrive wrapped in so the
    UI renders prose rather than raw `<p>` tags.
    """
    for candidate in (
        entry.get("summary"),
        _first_content_value(entry.get("content")),
        entry.get("subtitle"),
        entry.get("description"),
    ):
        text = _to_plain_text(candidate)
        if text:
            return text
    return ""


def _first_content_value(content: object) -> object:
    """feedparser models `<content:encoded>` as a list of `{value, type}` dicts."""
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return first.get("value")
    return None


def _to_plain_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = _WHITESPACE.sub(" ", unescape(_HTML_TAG.sub(" ", value))).strip()
    if len(text) <= _MAX_SUMMARY_CHARS:
        return text
    return text[:_MAX_SUMMARY_CHARS].rstrip() + _ELLIPSIS
