from pydantic import BaseModel, Field

from app.application.consequence.consequence_edge_draft import ConsequenceEdgeDraft
from app.application.consequence.consequence_node_draft import ConsequenceNodeDraft


class ConsequenceChainExtraction(BaseModel):
    """Structured-output schema the Consequence Chain Analyst asks the chat model to fill in.

    Passed to `LLMProvider.complete_structured(...)` in `generate_consequence_chain.py` —
    mirrors `SignalClassification`'s role for the Analyst pipeline
    (`application/signals/signal_classification.py`), just for causal-chain extraction
    instead of impact classification.

    Nodes are addressed positionally (`ConsequenceEdgeDraft.source_index`/`target_index`
    into `nodes`) rather than by a model-generated string id: LLMs are unreliable at
    inventing and then consistently re-using arbitrary ids across a structured-output
    call, while a 0-based list index is unambiguous and trivial to validate/clamp.
    `GenerateConsequenceChain` assigns the real `ConsequenceNode.id` values afterward.
    """

    nodes: list[ConsequenceNodeDraft] = Field(
        min_length=3,
        description=(
            "Ordered causal states from the root event/instrument to its downstream "
            "effects, e.g. X, Y, Z for a second-order chain."
        ),
    )
    edges: list[ConsequenceEdgeDraft] = Field(
        min_length=2,
        description=(
            "Causal edges connecting the nodes above, each with its own mechanism and confidence."
        ),
    )
