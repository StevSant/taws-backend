from operator import add
from typing import Annotated, NotRequired

from langgraph.graph import MessagesState

from app.infrastructure.agents.contribution import Contribution


class SupervisorState(MessagesState):
    """Messages plus supervisor routes, parallel contributions, and reply context.

    `routes` is written by the supervisor and read by `select_specialist_routes`: one route
    keeps the direct edge, while multiple routes become parallel contributor `Send` jobs.
    `contributions` uses an additive reducer for those parallel writes and is reset with
    `Overwrite([])` by the supervisor at the start of every turn.

    `grounding_context` (issue #73) is an optional pre-formatted string describing one
    specific asset or news article the user referenced; when present, the specialist node
    prepends it as a `SystemMessage` to anchor its reply (see `specialist_node_factory`).
    It's supplied on the initial input state (or omitted), hence `NotRequired`.

    `locale` (issue #67) travels the other way: `LangGraphAgentRunner.stream` writes it into
    the input state on every turn, and the supervisor + specialist nodes read it back to
    append `build_locale_instruction(locale)` to their system prompts. `NotRequired` because a
    checkpointed thread written before this field existed replays without it — nodes fall back
    to the English-authored personas alone, which is exactly the old behavior rather than a
    crash.

    The state is how locale reaches the NODES, and it is deliberately not the only channel: the
    same turn's locale also goes into the graph run's `configurable` (see
    `locale_config_key.py`). Tools are invoked by `invoke_with_bound_tools` from inside a node
    and never receive the state, so the config is the only channel that reaches them — see
    `tools/resolve_tool_locale.py`. Both carry the same value from the same `ResolveLocale`
    call, so they cannot disagree; if you add a locale consumer, pick the channel by whether it
    is handed the `state`.
    """

    routes: NotRequired[list[str]]
    contributor_route: NotRequired[str]
    contributions: Annotated[list[Contribution], add]
    grounding_context: NotRequired[str]
    locale: NotRequired[str]
