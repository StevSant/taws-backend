from typing import Any

from app.infrastructure.realtime.tools.args import GetNewsArgs


async def handle_get_news(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    """Return recent news items, optionally scoped to one instrument symbol.

    Delegates to `NewsProvider.fetch_news`. Each item is flattened to just what the voice
    model needs to talk about it (title/source/date/url), keeping the payload small.
    `user_id` is unused — news is public — but part of the uniform handler signature.
    """
    typed: GetNewsArgs = args
    symbols = [typed.symbol.upper()] if typed.symbol else None

    provider = container.get_news_provider()
    items = await provider.fetch_news(symbols=symbols, limit=typed.limit)

    return {
        "count": len(items),
        "items": [
            {
                "title": item.title,
                "summary": item.summary,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at.isoformat(),
            }
            for item in items[: typed.limit]
        ],
    }
