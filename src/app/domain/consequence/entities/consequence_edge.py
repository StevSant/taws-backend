from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConsequenceEdge:
    """One causal link between two `ConsequenceNode`s in a `ConsequenceChain`.

    `source_node_id` / `target_node_id` reference `ConsequenceNode.id` values from the
    same chain. `mechanism` is the (non-fabricated, model-grounded) explanation of *why*
    the source plausibly leads to the target; `confidence` is this specific edge's
    likelihood, independent of the other edges in the chain — a long chain typically has
    decreasing confidence hop over hop, but that's a property of the generated data, not
    enforced here.
    """

    source_node_id: str
    target_node_id: str
    mechanism: str
    confidence: float
