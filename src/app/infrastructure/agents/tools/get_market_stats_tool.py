from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.quant.market_stats import MarketStats
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.application.quant.use_cases.compute_market_stats import ComputeMarketStats

_DEFAULT_WINDOW_DAYS = 30


class _GetMarketStatsArgs(BaseModel):
    instrument_symbol: str = Field(
        description="The instrument symbol to compute market stats for, e.g. AAPL or BTC."
    )
    window_days: int = Field(
        default=_DEFAULT_WINDOW_DAYS,
        description="How many days of price history to compute the stats over.",
        ge=2,
        le=365,
    )


def build_get_market_stats_tool(compute_market_stats: ComputeMarketStats) -> StructuredTool:
    """Build a LangChain tool wrapping `ComputeMarketStats` for the `quant` specialist.

    Thin wrapper only: all the actual price-delta/volatility/unusual-move math lives in
    `ComputeMarketStats` (`application/quant/use_cases/compute_market_stats.py`), so it
    stays reusable by `GET /api/v1/quant/stats` and, later, the Scenario Simulation graph
    (issue #12) — see that use case's docstring. Bound only to the `quant` specialist
    node (see `specialist_node_factory.py` / `supervisor_graph.py`) —
    `analyst`/`advisor` are unaffected.
    """

    async def _run(instrument_symbol: str, window_days: int = _DEFAULT_WINDOW_DAYS) -> str:
        try:
            stats = await compute_market_stats.execute(instrument_symbol.upper(), window_days)
        except UnknownInstrumentError as exc:
            return str(exc)
        return _format_market_stats(stats)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_market_stats",
        description=(
            "Compute real price delta, annualized volatility (with a regime label), and "
            "unusual-move flags for one instrument symbol over a window of days. Use this "
            "before answering any question about an instrument's recent price behavior, "
            "volatility, or unusual moves — never invent numbers."
        ),
        args_schema=_GetMarketStatsArgs,
    )


def _format_market_stats(stats: MarketStats) -> str:
    volatility = (
        f"{stats.volatility_pct:.2f}% ({stats.volatility_regime.value})"
        if stats.volatility_pct is not None and stats.volatility_regime is not None
        else "unavailable (not enough price history)"
    )
    delta = f"{stats.price_delta_pct:.2f}%" if stats.price_delta_pct is not None else "unavailable"
    last_price = f"{stats.last_price:.4f}" if stats.last_price is not None else "unavailable"

    lines = [
        f"{stats.instrument_symbol} — {stats.window_days}-day stats as of "
        f"{stats.as_of.date().isoformat()}:",
        f"- last price: {last_price}",
        f"- price delta over window: {delta}",
        f"- annualized volatility: {volatility}",
    ]
    if stats.unusual_moves:
        lines.append("- unusual moves:")
        lines.extend(
            f"  - [{move.date.date().isoformat()}] {move.return_pct:+.2f}% (z={move.z_score:+.2f})"
            for move in stats.unusual_moves
        )
    else:
        lines.append("- unusual moves: none flagged in this window")
    return "\n".join(lines)
