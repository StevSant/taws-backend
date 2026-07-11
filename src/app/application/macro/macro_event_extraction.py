from pydantic import BaseModel, Field

from app.application.macro.macro_asset_class_impact_draft import MacroAssetClassImpactDraft


class MacroEventExtraction(BaseModel):
    """Structured-output schema the Macro Analyst asks the chat model to fill in.

    Passed to `LLMProvider.complete_structured(...)` in `interpret_macro_event.py` —
    mirrors `ConsequenceChainExtraction`'s role for the Consequence Chain Analyst
    (`application/consequence/consequence_chain_extraction.py`), just for per-asset-class
    macro impact tagging instead of causal-chain extraction.
    """

    asset_class_impacts: list[MacroAssetClassImpactDraft] = Field(
        min_length=1,
        description=(
            "One impact call per requested asset class, tagging direction and magnitude, "
            "grounded strictly in the provided macro figures and event description."
        ),
    )
