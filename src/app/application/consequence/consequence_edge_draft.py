from pydantic import BaseModel, Field


class ConsequenceEdgeDraft(BaseModel):
    """One causal edge the model proposes, referencing `ConsequenceChainExtraction.nodes`
    by position rather than by an id it would have to invent and keep consistent.

    `GenerateConsequenceChain` resolves `source_index`/`target_index` into the real
    `ConsequenceNode.id` values it assigns after extraction — see that use case's
    `_to_chain` for the resolution (with out-of-range indices clamped, never crashing on
    a malformed model response).
    """

    source_index: int = Field(
        ge=0, description="0-based index into `nodes` for the cause side of this edge."
    )
    target_index: int = Field(
        ge=0, description="0-based index into `nodes` for the effect side of this edge."
    )
    mechanism: str = Field(
        description=(
            "One or two sentences explaining *why* the source plausibly leads to the "
            "target. Never invent facts outside general causal reasoning."
        )
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence this specific edge holds, from 0.0 to 1.0."
    )
