import asyncio

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.domain.market.entities import MacroObservation, VolatilityRegime
from app.domain.market.ports import MacroDataProvider


class _GetMacroStateArgs(BaseModel):
    """No arguments: the macro state is market-wide, same visibility as `GET /api/v1/macro`."""


def build_get_macro_state_tool(macro_data_provider: MacroDataProvider) -> StructuredTool:
    """Build the tool exposing the raw current macro snapshot to chat.

    Same three reads as `GET /api/v1/macro` (FRED policy rate + CPI, VIX regime), fetched
    concurrently and formatted as numbers — no LLM in the loop. The `macro` specialist's
    other tool (`interpret_macro_event`) runs a full reasoning pipeline that wants an
    event description; for "how are rates / the VIX today?" that is an expensive detour,
    and the `advisor` had no macro access at all. Each reading degrades independently, so
    one dark FRED series doesn't blank the other two.
    """

    async def _run() -> str:
        rates, cpi, volatility = await asyncio.gather(
            macro_data_provider.get_rates(),
            macro_data_provider.get_cpi(),
            macro_data_provider.get_volatility_regime(),
            return_exceptions=True,
        )
        lines = [
            "Current macro state (latest available observations):",
            _observation_line("policy rate", rates, unit="%"),
            _observation_line("CPI (raw index level, NOT a yearly inflation rate)", cpi),
            _volatility_line(volatility),
            "Report only these figures; if one is unavailable say so — do not estimate it.",
        ]
        return "\n".join(lines)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_macro_state",
        description=(
            "Fetch the real current macro snapshot: the policy interest rate, the latest "
            "CPI index observation, and the VIX level with its volatility-regime label. "
            "Always call this before answering any question about current rates, "
            "inflation data, the VIX, or overall macro conditions — never quote these "
            "from memory."
        ),
        args_schema=_GetMacroStateArgs,
    )


def _observation_line(label: str, result: MacroObservation | BaseException, unit: str = "") -> str:
    if isinstance(result, BaseException):
        return f"- {label}: UNAVAILABLE right now ({result})"
    return (
        f"- {label} [{result.series_id}]: {result.value:.2f}{unit} "
        f"as of {result.as_of.date().isoformat()}"
    )


def _volatility_line(result: VolatilityRegime | BaseException) -> str:
    if isinstance(result, BaseException):
        return f"- VIX / volatility regime: UNAVAILABLE right now ({result})"
    return (
        f"- VIX: {result.vix_level:.1f} ({result.regime.value} regime) "
        f"as of {result.as_of.date().isoformat()}"
    )
