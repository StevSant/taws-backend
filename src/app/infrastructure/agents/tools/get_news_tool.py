from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.market.entities import NewsItem
from app.domain.market.ports import NewsProvider


class _GetNewsArgs(BaseModel):
    symbol: str | None = Field(
        default=None,
        description=(
            "Optional instrument symbol, e.g. AAPL or BTC. Omit it for the most important "
            "recent market-wide news."
        ),
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of recent news items to return.",
    )


def build_get_news_tool(news_provider: NewsProvider) -> StructuredTool:
    """Build the Analyst tool that exposes dated, sourced news to text chat."""

    async def _run(symbol: str | None = None, limit: int = 5) -> str:
        symbols = [symbol.upper()] if symbol else None
        fetch_limit = limit if symbol else min(limit * 5, 50)
        items = await news_provider.fetch_news(symbols=symbols, limit=fetch_limit)
        if not items:
            scope = symbol.upper() if symbol else "the market"
            return f"No recent news was found for {scope}. Do not infer or invent events."
        if not symbol:
            items.sort(key=lambda item: bool(item.related_symbols), reverse=True)
        return _format_news(items[:limit])

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_news",
        description=(
            "Fetch real recent market news with exact title, publisher, publication date, URL, "
            "and related symbols. Always call this before answering about current/recent news "
            "or what is happening in markets. Omit symbol for broad market news. Never replace "
            "its results with remembered headlines."
        ),
        args_schema=_GetNewsArgs,
    )


def _format_news(items: list[NewsItem]) -> str:
    lines = [
        "Recent sourced news (items linked to tracked instruments are prioritized):",
        (
            "For requested impact/confidence, call generate_signal for up to three unique "
            "related symbols before answering. An unlinked item cannot support an "
            "instrument-level impact assessment."
        ),
    ]
    if any(item.provider == "fixture" for item in items):
        lines.append("DATA MODE: demonstration fixture data; disclose this to the user.")
    for item in items:
        symbols = ", ".join(item.related_symbols) or "not identified"
        lines.extend(
            [
                f"- [{item.published_at.isoformat()}] {item.source}: {item.title}",
                f"  related symbols: {symbols}",
                f"  summary: {item.summary or 'No summary available.'}",
                f"  url: {item.url}",
            ]
        )
    return "\n".join(lines)
