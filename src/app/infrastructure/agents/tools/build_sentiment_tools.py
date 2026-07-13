from langchain_core.tools import BaseTool

from app.application.sentiment.use_cases import AnalyzeSentiment
from app.infrastructure.agents.tools.analyze_sentiment_tool import build_analyze_sentiment_tool


def build_sentiment_tools(use_case: AnalyzeSentiment, default_locale: str) -> list[BaseTool]:
    """Build the tools bound only to the `sentiment` specialist node.

    Wraps the reusable `AnalyzeSentiment` use case
    (`application/sentiment/use_cases/analyze_sentiment.py`) as a single LangChain tool
    so the Sentiment Analyst always produces a grounded tone score + Fear & Greed reading
    instead of reasoning about sentiment from memory. See `Container._get_chat_graph` for
    where this gets wired in, and `build_consequence_tools.py` for the sibling pattern
    this mirrors.

    `default_locale` is only the fallback — the tool prefers the turn's locale from its injected
    `RunnableConfig` (see `resolve_tool_locale`).
    """
    return [build_analyze_sentiment_tool(use_case, default_locale)]
