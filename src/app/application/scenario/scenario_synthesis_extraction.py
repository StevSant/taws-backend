from pydantic import BaseModel, Field

from app.application.scenario.scenario_asset_class_synthesis_draft import (
    ScenarioAssetClassSynthesisDraft,
)


class ScenarioSynthesisExtraction(BaseModel):
    """Structured-output schema the Synthesis step asks the chat model to fill in —
    mirrors `ConsequenceChainExtraction`'s role for the Consequence Chain Analyst
    (`application/consequence/consequence_chain_extraction.py`).

    Passed to `LLMProvider.complete_structured(...)` in
    `synthesize_scenario_result.py`, grounded in the gathered `ScenarioContext`, quant
    results, and `ConsequenceChain` — the model never sees a bare scenario description
    with no supporting data.
    """

    title: str = Field(description="A short human-readable title for this synthesized result.")
    narrative: str = Field(
        description=(
            "A short (2-4 sentence) overall synthesis paragraph, grounded strictly in the "
            "provided context, causal chain, and quant stats — never invent facts outside "
            "them, and never phrase this as trading/execution instructions."
        )
    )
    impact_map: list[ScenarioAssetClassSynthesisDraft] = Field(
        min_length=1,
        description="One impact call per requested asset class listed in the prompt.",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description=(
            "Research/monitoring actions only, e.g. 'Watch NVDA's next earnings call', "
            "'Set an alert on TLT volatility' — never buy/sell/order/execution instructions."
        ),
    )
