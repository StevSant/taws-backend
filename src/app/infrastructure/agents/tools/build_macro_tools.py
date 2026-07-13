from langchain_core.tools import BaseTool

from app.application.macro.use_cases import InterpretMacroEvent
from app.infrastructure.agents.tools.interpret_macro_event_tool import (
    build_interpret_macro_event_tool,
)


def build_macro_tools(use_case: InterpretMacroEvent, default_locale: str) -> list[BaseTool]:
    """Build the tools bound only to the `macro` specialist node.

    Wraps the reusable `InterpretMacroEvent` use case
    (`application/macro/use_cases/interpret_macro_event.py`) as a single LangChain tool
    so the Macro Analyst always grounds its asset-class tagging in real FRED/VIX figures
    instead of reasoning about macro conditions from memory. See
    `Container._get_chat_graph` for where this gets wired in, and
    `build_consequence_tools.py` for the sibling pattern this mirrors.

    `default_locale` is only the fallback — the tool prefers the turn's locale from its injected
    `RunnableConfig` (see `resolve_tool_locale`).
    """
    return [build_interpret_macro_event_tool(use_case, default_locale)]
