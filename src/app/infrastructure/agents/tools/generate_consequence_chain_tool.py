from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.consequence.use_cases import GenerateConsequenceChain
from app.domain.consequence.entities import ConsequenceChain


class _GenerateConsequenceChainArgs(BaseModel):
    subject: str = Field(
        min_length=1,
        description=(
            "The event or instrument to reason about, e.g. 'Fed raises rates 50bps' or 'AAPL'."
        ),
    )


def build_generate_consequence_chain_tool(use_case: GenerateConsequenceChain) -> StructuredTool:
    """Build a LangChain tool wrapping `GenerateConsequenceChain` for the `consequence`
    specialist node — thin wrapper, same shape as `get_signals_for_instrument_tool.py`.

    Bound only to the `consequence` specialist node (see `specialist_node_factory.py` /
    `supervisor_graph.py`) — the other specialists are unaffected. The wrapped use case is
    the same reusable `GenerateConsequenceChain.execute(subject)` also called directly by
    `POST /api/v1/consequence-chains/generate`, so a chain generated through chat and one
    generated through the REST endpoint always come from the same code path.
    """

    async def _run(subject: str) -> str:
        chain = await use_case.execute(subject)
        return _format_chain(chain)

    return StructuredTool.from_function(
        coroutine=_run,
        name="generate_consequence_chain",
        description=(
            "Generate a structured second-order causal chain (X -> Y -> Z) for an event or "
            "instrument, with a mechanism and confidence on every edge. Always call this "
            "before answering a causal-chain question — never reason about consequences "
            "from memory alone."
        ),
        args_schema=_GenerateConsequenceChainArgs,
    )


def _format_chain(chain: ConsequenceChain) -> str:
    node_labels = {node.id: node.label for node in chain.nodes}
    lines = [
        f"- {node_labels.get(edge.source_node_id, edge.source_node_id)} -> "
        f"{node_labels.get(edge.target_node_id, edge.target_node_id)} "
        f"(confidence={edge.confidence:.2f}): {edge.mechanism}"
        for edge in chain.edges
    ]
    header = f"Subject: {chain.subject}"
    return f"{header}\n\n" + "\n".join(lines) + f"\n\n{chain.disclaimer}"
