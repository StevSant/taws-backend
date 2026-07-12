from langchain_core.tools import BaseTool

from app.application.signals.use_cases import GenerateSignal
from app.domain.market.ports import NewsProvider
from app.infrastructure.agents.tools.generate_signal_tool import build_generate_signal_tool
from app.infrastructure.agents.tools.get_news_tool import build_get_news_tool


def build_analyst_grounding_tools(
    news_provider: NewsProvider,
    generate_signal: GenerateSignal,
    default_locale: str,
) -> list[BaseTool]:
    """Wire existing live-news and RAG signal capabilities into the Analyst."""

    return [
        build_get_news_tool(news_provider),
        build_generate_signal_tool(generate_signal, default_locale),
    ]
