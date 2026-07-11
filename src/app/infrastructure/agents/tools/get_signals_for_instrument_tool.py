from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository


class _GetSignalsForInstrumentArgs(BaseModel):
    instrument_symbol: str = Field(
        description=(
            "The instrument symbol to look up persisted Analyst signals for, e.g. AAPL or BTC."
        )
    )


def build_get_signals_for_instrument_tool(signal_repository: SignalRepository) -> StructuredTool:
    """Build a LangChain tool grounding the Advisor's answers in persisted `Signal`s.

    Bound only to the `advisor` specialist node (see `specialist_node_factory.py` /
    `supervisor_graph.py`) — `analyst`/`quant` are unaffected.
    """

    async def _run(instrument_symbol: str) -> str:
        signals = await signal_repository.list_for_instrument(instrument_symbol.upper())
        if not signals:
            return f"No persisted signals found for {instrument_symbol.upper()}."
        return "\n".join(_format_signal(signal) for signal in signals)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_signals_for_instrument",
        description=(
            "Look up persisted Analyst signals (impact class, confidence, dated/sourced "
            "evidence) for one instrument symbol. Use this before answering any question "
            "about an instrument's outlook — never answer from memory alone."
        ),
        args_schema=_GetSignalsForInstrumentArgs,
    )


def _format_signal(signal: Signal) -> str:
    evidence = "; ".join(
        f"{item.source} ({item.published_at.date().isoformat()})" for item in signal.evidence
    )
    return (
        f"- [{signal.created_at.date().isoformat()}] impact={signal.impact_class.value} "
        f"confidence={signal.confidence:.2f} price_delta={signal.price_delta} "
        f"evidence=[{evidence}]"
    )
