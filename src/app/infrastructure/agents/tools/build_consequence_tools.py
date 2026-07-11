from langchain_core.tools import BaseTool

from app.application.consequence.use_cases import GenerateConsequenceChain
from app.infrastructure.agents.tools.generate_consequence_chain_tool import (
    build_generate_consequence_chain_tool,
)


def build_consequence_tools(use_case: GenerateConsequenceChain) -> list[BaseTool]:
    """Build the tools bound only to the `consequence` specialist node.

    Wraps the reusable `GenerateConsequenceChain` use case
    (`application/consequence/use_cases/generate_consequence_chain.py`) as a single
    LangChain tool so the Consequence Chain Analyst always produces a structured chain
    instead of reasoning about causality from memory. See `Container._get_chat_graph`
    for where this gets wired in, and `build_advisor_grounding_tools.py` for the sibling
    pattern this mirrors.
    """
    return [build_generate_consequence_chain_tool(use_case)]
