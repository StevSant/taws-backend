from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.compliance import ComplianceViolationError
from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.application.signals.use_cases import GenerateSignal
from app.domain.signals.entities import Signal
from app.infrastructure.agents.tools.resolve_tool_locale import resolve_tool_locale


class _GenerateSignalArgs(BaseModel):
    symbol: str = Field(
        min_length=1,
        description="Instrument symbol to analyze, e.g. AAPL, NVDA, BTC, or ETH.",
    )


def build_generate_signal_tool(
    use_case: GenerateSignal,
    default_locale: str,
) -> StructuredTool:
    """Build the Analyst tool over the existing news + price + RAG signal pipeline.

    The signal's thesis, drivers and risks are LLM-written prose, so the locale isn't
    cosmetic here — it's what the pipeline generates in. It comes from the turn's
    `RunnableConfig` (see `resolve_tool_locale`), falling back to `default_locale` when
    there's no per-turn locale to read.
    """

    async def _run(symbol: str, config: RunnableConfig) -> str:
        normalized_symbol = symbol.upper()
        try:
            signal = await use_case.execute(
                normalized_symbol, resolve_tool_locale(config, default_locale)
            )
        except (UnknownInstrumentError, InsufficientEvidenceError, ComplianceViolationError) as exc:
            return f"Signal unavailable: {exc}. Do not estimate or invent a replacement."
        return _format_signal(signal)

    return StructuredTool.from_function(
        coroutine=_run,
        name="generate_signal",
        description=(
            "Run the existing grounded Analyst pipeline for one instrument. It combines recent "
            "dated news, price context, and RAG-retrieved historical analogs to return impact, "
            "confidence, thesis, drivers, risks, and evidence. Call it when the user asks how "
            "news affects a specific instrument. Do not invent an impact if it reports "
            "insufficient evidence."
        ),
        args_schema=_GenerateSignalArgs,
    )


def _format_signal(signal: Signal) -> str:
    lines = [
        f"Grounded signal for {signal.instrument_symbol} as of {signal.created_at.isoformat()}:",
        f"- impact: {signal.impact_class.value}",
        f"- confidence: {signal.confidence:.0%}",
        f"- price delta: {signal.price_delta if signal.price_delta is not None else 'unavailable'}",
        f"- analysis available: {signal.analysis_available}",
        f"- thesis: {signal.thesis or 'No thesis available.'}",
        "- key drivers:",
    ]
    lines.extend(f"  - {driver}" for driver in signal.key_drivers)
    if not signal.key_drivers:
        lines.append("  - none provided")
    lines.append("- risk factors:")
    lines.extend(f"  - {risk}" for risk in signal.risk_factors)
    if not signal.risk_factors:
        lines.append("  - none provided")
    lines.append("- dated evidence:")
    lines.extend(
        (
            f"  - [{item.published_at.isoformat()}] {item.source}: "
            f"{item.detail or 'Supporting evidence'}" + (f" — {item.url}" if item.url else "")
        )
        for item in signal.evidence
    )
    if not signal.evidence:
        lines.append("  - none")
    lines.append(signal.disclaimer)
    return "\n".join(lines)
