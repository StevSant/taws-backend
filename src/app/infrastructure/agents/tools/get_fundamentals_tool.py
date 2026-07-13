import asyncio

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.market.entities import EarningsCalendarEntry, InstrumentFundamentals
from app.domain.market.errors import FundamentalsUnavailableError
from app.domain.market.ports import FundamentalsProvider


class _GetFundamentalsArgs(BaseModel):
    instrument_symbol: str = Field(
        min_length=1,
        description="The instrument symbol to fetch fundamentals for, e.g. AAPL or MSFT.",
    )


def build_get_fundamentals_tool(fundamentals_provider: FundamentalsProvider) -> StructuredTool:
    """Build the tool exposing real fundamentals + the earnings calendar to chat.

    Thin wrapper over the same `FundamentalsProvider` port behind
    `GET /api/v1/fundamentals/{symbol}` (yfinance adapter), so chat and the REST surface
    can never disagree on a P/E or an earnings date. Bound to the `analyst` and `advisor`
    specialists — before this tool, "when does NVDA report earnings?" had no grounded
    answer anywhere in chat. Public market data, so it passes the same chat-route safety
    test as `get_market_stats`.
    """

    async def _run(instrument_symbol: str) -> str:
        symbol = instrument_symbol.upper()
        try:
            fundamentals, earnings = await asyncio.gather(
                fundamentals_provider.get_fundamentals(symbol),
                fundamentals_provider.get_earnings_calendar(symbol),
            )
        except FundamentalsUnavailableError as exc:
            return (
                f"Fundamentals for {symbol} are UNAVAILABLE — the upstream provider could "
                f"not be reached ({exc}). Tell the user the data is unavailable right now "
                f"and suggest retrying shortly. Do NOT state or estimate a P/E, market "
                f"cap, dividend yield, or earnings date from memory."
            )
        return _format_fundamentals(fundamentals, earnings)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_fundamentals",
        description=(
            "Fetch real fundamentals for one instrument: market cap, P/E ratio, dividend "
            "yield, sector, and the next scheduled earnings date with an upcoming-earnings "
            "risk flag. Always call this before answering any valuation, earnings-date, or "
            "company-profile question — never quote these figures from memory."
        ),
        args_schema=_GetFundamentalsArgs,
    )


def _format_fundamentals(
    fundamentals: InstrumentFundamentals, earnings: EarningsCalendarEntry | None
) -> str:
    lines = [
        f"{fundamentals.symbol} fundamentals (missing fields mean the instrument has no "
        f"such figure — e.g. crypto/FX — or the provider lacks it; never fill them in):",
        f"- market cap: {_number(fundamentals.market_cap)}",
        f"- P/E ratio: {_number(fundamentals.pe_ratio)}",
        f"- dividend yield: {_percent(fundamentals.dividend_yield)}",
        f"- sector: {fundamentals.sector or 'unavailable'}",
    ]
    if earnings is None:
        lines.append("- next earnings date: none scheduled / not applicable")
    else:
        risk = (
            " — WITHIN the upcoming-earnings risk window, flag the event risk"
            if earnings.is_upcoming_risk
            else ""
        )
        lines.append(f"- next earnings date: {earnings.earnings_date.date().isoformat()}{risk}")
    return "\n".join(lines)


def _number(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "unavailable"


def _percent(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "unavailable"
