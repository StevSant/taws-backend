from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.application.quant.use_cases.compute_event_study import ComputeEventStudy

_DEFAULT_LOOKBACK_DAYS = 365
_DEFAULT_MOVE_THRESHOLD_PCT = 3.0


class _GetEventStudyStatsArgs(BaseModel):
    instrument_symbol: str = Field(
        description="The instrument symbol to run the event study for, e.g. AAPL or BTC."
    )
    lookback_days: int = Field(
        default=_DEFAULT_LOOKBACK_DAYS,
        description="How many days of price history to search for similar events.",
        ge=2,
        le=365,
    )
    move_threshold_pct: float = Field(
        default=_DEFAULT_MOVE_THRESHOLD_PCT,
        description=(
            "Minimum absolute daily move (in percent) for a day to count as a "
            "'similar event', e.g. 3.0 for +/-3% days."
        ),
        gt=0,
    )


def build_get_event_study_stats_tool(compute_event_study: ComputeEventStudy) -> StructuredTool:
    """Build a LangChain tool wrapping `ComputeEventStudy` for the `quant` specialist.

    Thin wrapper only: all the actual "similar events" matching and median/range math
    lives in `ComputeEventStudy` (`application/quant/use_cases/compute_event_study.py`),
    kept reusable by `GET /api/v1/quant/event-study` and, later, the Scenario Simulation
    graph (issue #12) — see that use case's docstring for what "similar event" means
    here (a T1 simplification, not the historical-analogs RAG scope of issue #15). Bound
    only to the `quant` specialist node — `analyst`/`advisor` are unaffected.
    """

    async def _run(
        instrument_symbol: str,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        move_threshold_pct: float = _DEFAULT_MOVE_THRESHOLD_PCT,
    ) -> str:
        try:
            stats = await compute_event_study.execute(
                instrument_symbol.upper(), lookback_days, move_threshold_pct
            )
        except UnknownInstrumentError as exc:
            return str(exc)
        return _format_event_study_stats(stats)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_event_study_stats",
        description=(
            "Compute event-study statistics for one instrument symbol: how many past days "
            "in the lookback window moved by at least the given threshold, and the "
            "median/min/max size of those moves. Use this to answer 'how did similar moves "
            "play out historically' questions with real numbers, never invented ones."
        ),
        args_schema=_GetEventStudyStatsArgs,
    )


def _format_event_study_stats(stats: EventStudyStats) -> str:
    header = (
        f"{stats.instrument_symbol} — event study over the last {stats.lookback_days} days "
        f"(events = days moving >= {stats.move_threshold_pct:.2f}%):"
    )
    if stats.sample_size == 0:
        return f"{header}\nNo similar events found in this window."

    lines = [
        header,
        f"- sample size: {stats.sample_size}",
        f"- median move: {stats.median_return_pct:+.2f}%",
        f"- range: {stats.min_return_pct:+.2f}% to {stats.max_return_pct:+.2f}%",
        "- most recent matched events:",
    ]
    lines.extend(
        f"  - [{event.date.date().isoformat()}] {event.return_pct:+.2f}%" for event in stats.events
    )
    return "\n".join(lines)
