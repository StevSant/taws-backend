from pydantic import BaseModel, Field

from app.application.scenario.scenario_asset_class_synthesis_draft import (
    ScenarioAssetClassSynthesisDraft,
)


class ScenarioConsensusExtraction(BaseModel):
    summary: str = Field(description="Short synthesis of the specialist panel.")
    conclusion: str = Field(description="Midas' grounded final conclusion.")
    agreements: list[str] = Field(default_factory=list, max_length=6)
    disagreements: list[str] = Field(default_factory=list, max_length=6)
    uncertainties: list[str] = Field(default_factory=list, max_length=6)
    # Optional with a 0.0 default, mirroring the domain `ScenarioConsensus.confidence`. Under
    # `strict: False` structured output OpenAI does not enforce required fields, and models
    # reliably DROP this one nested scalar when it carries no description — which failed schema
    # validation on every attempt and 503'd the whole run (the sibling
    # `ScenarioAssetClassSynthesisDraft.confidence`, which IS described, was never dropped). A
    # description now nudges the model to fill it; the default keeps one missing scalar from
    # nuking an otherwise-complete, grounded synthesis.
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the consensus conclusion, from 0.0 to 1.0.",
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
    consensus: ScenarioConsensusExtraction = Field(
        description=(
            "Consensus synthesized from the supplied real specialist contributions. "
            "It is not a vote; preserve material disagreement and uncertainty."
        )
    )
