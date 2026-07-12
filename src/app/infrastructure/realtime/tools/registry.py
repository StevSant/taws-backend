from typing import Any

from app.infrastructure.realtime.tools.args import (
    GenerateSignalArgs,
    GetMarketDataArgs,
    GetNewsArgs,
    GetNotesArgs,
    GetWatchlistArgs,
    ListSignalsArgs,
)
from app.infrastructure.realtime.tools.handlers import (
    handle_generate_signal,
    handle_get_market_data,
    handle_get_news,
    handle_get_notes,
    handle_get_watchlist,
    handle_list_signals,
)
from app.infrastructure.realtime.tools.realtime_tool import RealtimeTool
from app.infrastructure.realtime.tools.tool_not_found_error import ToolNotFoundError

# The single source of truth for which realtime tools exist and how each is validated +
# dispatched. Adding a tool = add one `RealtimeTool` here (plus its arg model + handler);
# the schema list, the allowlist, and dispatch all derive from this dict, so they can't
# drift apart.
_REALTIME_TOOLS: dict[str, RealtimeTool] = {
    "get_market_data": RealtimeTool(
        name="get_market_data",
        description=(
            "Get the latest price and a recent daily price series for one tracked "
            "instrument (stock, crypto, commodity, or forex) by its symbol."
        ),
        args_model=GetMarketDataArgs,
        handler=handle_get_market_data,
    ),
    "get_news": RealtimeTool(
        name="get_news",
        description=(
            "Get recent market news, optionally scoped to one instrument symbol. Each "
            "item includes its source and publication date."
        ),
        args_model=GetNewsArgs,
        handler=handle_get_news,
    ),
    "list_signals": RealtimeTool(
        name="list_signals",
        description=(
            "List the Analyst's recorded impact signals (impact class, confidence, "
            "thesis) for one instrument symbol."
        ),
        args_model=ListSignalsArgs,
        handler=handle_list_signals,
    ),
    "generate_signal": RealtimeTool(
        name="generate_signal",
        description=(
            "Run the Analyst pipeline on demand for one instrument and return the newly "
            "generated impact signal. Slower than list_signals — acknowledge before calling."
        ),
        args_model=GenerateSignalArgs,
        handler=handle_generate_signal,
    ),
    "get_watchlist": RealtimeTool(
        name="get_watchlist",
        description=(
            "Get the current user's own watchlists and the instruments tracked in each. "
            "Takes no arguments — always scoped to the authenticated user. Use when they "
            "ask about 'my watchlist' or what they are tracking."
        ),
        args_model=GetWatchlistArgs,
        handler=handle_get_watchlist,
    ),
    "get_notes": RealtimeTool(
        name="get_notes",
        description=(
            "Get the current user's own saved notes, most-recent first. Takes no arguments "
            "— always scoped to the authenticated user. Use when they ask about 'my notes' "
            "or what they wrote down."
        ),
        args_model=GetNotesArgs,
        handler=handle_get_notes,
    ),
}


def build_realtime_tool_schemas() -> list[dict[str, Any]]:
    """Return the OpenAI Realtime tool-declaration list for every registered tool.

    Flat `{"type": "function", "name", "description", "parameters"}` shape — the exact
    form `client.realtime.client_secrets.create`'s `session.tools` expects (verified
    against `openai.types.realtime.RealtimeFunctionToolParam`), NOT the Chat-Completions
    style nested under a `"function"` key.
    """
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_model.model_json_schema(),
        }
        for tool in _REALTIME_TOOLS.values()
    ]


def validate_tool_args(name: str, raw_arguments: dict[str, Any]) -> Any:
    """Look up `name` in the allowlist and validate `raw_arguments` against its schema.

    Raises `ToolNotFoundError` when `name` isn't a registered tool (allowlist gate) and
    `pydantic.ValidationError` when the arguments don't match the tool's schema. Kept
    separate from dispatch so the endpoint can distinguish "unknown tool" from "bad args"
    and map each to the right HTTP status without running any handler.
    """
    tool = _REALTIME_TOOLS.get(name)
    if tool is None:
        raise ToolNotFoundError(name)
    return tool.args_model.model_validate(raw_arguments)


async def dispatch_realtime_tool(
    container: Any, name: str, raw_arguments: dict[str, Any], user_id: str
) -> dict[str, Any]:
    """Validate + dispatch one realtime tool call, returning its JSON-serializable output.

    Security: `name` must be in the allowlist (`ToolNotFoundError` otherwise), arguments
    are validated by the tool's Pydantic model before the handler runs (`ValidationError`
    on bad input), and `user_id` comes from the verified JWT — it is passed to the handler
    positionally and NEVER read from `raw_arguments`.
    """
    typed_args = validate_tool_args(name, raw_arguments)
    tool = _REALTIME_TOOLS[name]
    return await tool.handler(container, typed_args, user_id)


def is_registered_tool(name: str) -> bool:
    """Return whether `name` is in the realtime tool allowlist."""
    return name in _REALTIME_TOOLS
