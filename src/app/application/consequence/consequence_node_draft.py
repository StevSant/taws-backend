from pydantic import BaseModel, Field


class ConsequenceNodeDraft(BaseModel):
    """One node the model proposes for a causal chain, before ids are assigned.

    Part of `ConsequenceChainExtraction` — see that class's docstring for why nodes are
    indexed positionally here instead of carrying model-generated ids.
    """

    label: str = Field(
        min_length=1,
        description=(
            "Short label for this state/event in the causal chain, e.g. "
            "'Fed raises rates 50bps' or 'Mortgage demand falls'."
        ),
    )
