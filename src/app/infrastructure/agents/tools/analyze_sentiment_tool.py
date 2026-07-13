from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.sentiment.unknown_instrument_error import UnknownInstrumentError
from app.application.sentiment.use_cases import AnalyzeSentiment
from app.domain.sentiment.entities import SentimentReading


class _AnalyzeSentimentArgs(BaseModel):
    instrument_symbol: str = Field(
        min_length=1,
        description="The instrument symbol to score news tone for, e.g. AAPL or BTC.",
    )


def build_analyze_sentiment_tool(use_case: AnalyzeSentiment, default_locale: str) -> StructuredTool:
    """Build a LangChain tool wrapping `AnalyzeSentiment` for the `sentiment` specialist
    node — thin wrapper, same shape as `generate_consequence_chain_tool.py`.

    Bound only to the `sentiment` specialist node (see `specialist_node_factory.py` /
    `supervisor_graph.py`). The wrapped use case is the same reusable
    `AnalyzeSentiment.execute(instrument_symbol, locale)` also called directly by
    `POST /api/v1/sentiment/{symbol}/analyze`, so a reading generated through chat and
    one generated through the REST endpoint always come from the same code path — and, since
    issue #29, hit the same `(symbol, locale)` cache.

    `default_locale` is injected (from `Settings`, via the DI container) rather than defaulted
    here — same pattern as `build_scenario_tools`. The chat graph has no per-turn locale to
    thread through a tool call, so the configured default is what a chat-initiated reading is
    cached under.
    """

    async def _run(instrument_symbol: str) -> str:
        try:
            reading = await use_case.execute(instrument_symbol.upper(), default_locale)
        except UnknownInstrumentError as exc:
            return str(exc)
        return _format_reading(reading)

    return StructuredTool.from_function(
        coroutine=_run,
        name="analyze_sentiment",
        description=(
            "Score real recent news tone (-1.0 to 1.0) for one instrument, and attach the "
            "current market-wide Fear & Greed Index reading. Always call this before "
            "answering a sentiment/tone question — never invent a tone score or Fear & "
            "Greed reading from memory."
        ),
        args_schema=_AnalyzeSentimentArgs,
    )


def _format_reading(reading: SentimentReading) -> str:
    fear_greed = reading.fear_greed
    lines = [
        f"{reading.instrument_symbol} sentiment as of {reading.created_at.date().isoformat()}:",
        f"- tone score: {reading.tone_score:+.2f} ({reading.tone_label.value})",
        f"- Fear & Greed Index: {fear_greed.value} ({fear_greed.classification.value}) as of "
        f"{fear_greed.as_of.date().isoformat()}",
        f"- rationale: {reading.rationale}",
    ]
    if reading.evidence:
        lines.append("- evidence:")
        lines.extend(
            f"  - [{item.published_at.date().isoformat()}] {item.source}: {item.detail}"
            for item in reading.evidence
        )
    else:
        lines.append("- evidence: no recent news available")
    lines.append(reading.disclaimer)
    return "\n".join(lines)
