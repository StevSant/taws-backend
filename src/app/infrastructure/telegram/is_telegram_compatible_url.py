from urllib.parse import urlparse


def is_telegram_compatible_url(url: str) -> bool:
    """Whether ``url`` is suitable for a Telegram inline URL button.

    Telegram rejects loopback URLs such as the local Angular development server. Callback
    buttons remain usable locally, so callers can simply omit the web-app button in that case.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    return (
        parsed.scheme in {"http", "https"}
        and hostname is not None
        and hostname not in {"localhost", "127.0.0.1", "::1"}
    )
