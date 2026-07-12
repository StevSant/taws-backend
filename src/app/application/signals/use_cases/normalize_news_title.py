import re


def normalize_news_title(title: str) -> str:
    """Normalize a news title for exact/near-duplicate comparison (issue #3's pre-filter):
    lowercase, collapse every run of non-alphanumeric characters to a single space, and
    strip. Cheap enough to run per-item; not a fuzzy/embedding similarity measure —
    catches the common case of the same wire story (e.g. "5 world market themes for the
    week ahead") appearing verbatim across several instruments' news feeds.
    """
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
