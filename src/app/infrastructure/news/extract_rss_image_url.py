from typing import Any
from urllib.parse import urlparse


def extract_rss_image_url(entry: Any) -> str | None:
    """Best-effort image URL from a feedparser entry."""
    media_thumbnail = entry.get("media_thumbnail")
    if isinstance(media_thumbnail, list) and media_thumbnail:
        url = media_thumbnail[0].get("url")
        if _is_http_url(url):
            return url

    media_content = entry.get("media_content")
    if isinstance(media_content, list):
        for media in media_content:
            url = media.get("url")
            medium = media.get("medium")
            if medium == "audio":
                continue
            if _is_http_url(url):
                return url

    for enclosure in entry.get("enclosures") or []:
        href = enclosure.get("href")
        mime = enclosure.get("type") or ""
        if mime.startswith("image/") and _is_http_url(href):
            return href

    for link in entry.get("links") or []:
        href = link.get("href")
        rel = link.get("rel") or ""
        mime = link.get("type") or ""
        if rel == "enclosure" and mime.startswith("image/") and _is_http_url(href):
            return href

    return None


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"}
