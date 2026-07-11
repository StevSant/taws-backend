from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.macro.use_cases import InterpretMacroEvent
from app.domain.macro.entities import MacroEventInterpretation


class _InterpretMacroEventArgs(BaseModel):
    event_description: str | None = Field(
        default=None,
        description=(
            "The macro event to interpret, e.g. 'Fed raises rates 50bps' or 'CPI print comes "
            "in hot at 4.1% YoY'. Omit to interpret the current macro state generally."
        ),
    )


def build_interpret_macro_event_tool(use_case: InterpretMacroEvent) -> StructuredTool:
    """Build a LangChain tool wrapping `InterpretMacroEvent` for the `macro` specialist
    node — thin wrapper, same shape as `generate_consequence_chain_tool.py`.

    Bound only to the `macro` specialist node (see `specialist_node_factory.py` /
    `supervisor_graph.py`). The wrapped use case is the same reusable
    `InterpretMacroEvent.execute(event_description)` also called directly by
    `POST /api/v1/macro/interpret`, so an interpretation generated through chat and one
    generated through the REST endpoint always come from the same code path.
    """

    async def _run(event_description: str | None = None) -> str:
        interpretation = await use_case.execute(event_description)
        return _format_interpretation(interpretation)

    return StructuredTool.from_function(
        coroutine=_run,
        name="interpret_macro_event",
        description=(
            "Interpret a macro event (rate decision, CPI print, Fed statement, ...) grounded "
            "in the real current FRED rate/CPI figures and VIX-derived volatility regime, "
            "tagging every asset class with a direction and magnitude. Always call this "
            "before answering a macro-event question — never invent rate/CPI/VIX numbers "
            "from memory."
        ),
        args_schema=_InterpretMacroEventArgs,
    )


def _format_interpretation(interpretation: MacroEventInterpretation) -> str:
    lines = [
        f"Event: {interpretation.event_description}",
        f"- {interpretation.rates.series_id} (policy rate): {interpretation.rates.value:.2f} "
        f"as of {interpretation.rates.as_of.date().isoformat()}",
        f"- {interpretation.cpi.series_id} (CPI): {interpretation.cpi.value:.2f} as of "
        f"{interpretation.cpi.as_of.date().isoformat()}",
        f"- VIX {interpretation.volatility_regime.vix_level:.2f} "
        f"({interpretation.volatility_regime.regime.value} regime) as of "
        f"{interpretation.volatility_regime.as_of.date().isoformat()}",
        "",
        "Asset class impacts:",
    ]
    lines.extend(
        f"- {impact.asset_class.value}: {impact.direction.value} "
        f"({impact.magnitude.value} magnitude) — {impact.rationale}"
        for impact in interpretation.asset_class_impacts
    )
    lines.append(interpretation.disclaimer)
    return "\n".join(lines)
