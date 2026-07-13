from typing import NotRequired

from langgraph.graph import MessagesState


class SupervisorState(MessagesState):
    """Graph state for `build_supervisor_graph`: `MessagesState` plus the chosen route
    and the reply locale.

    `route` is written by the supervisor node (see `supervisor_router_node.py`) and
    read by `select_specialist_route` to pick the conditional edge; it's absent from
    the initial input state (`NotRequired`), which is why it can't be a plain `str`.

    `locale` (issue #67) travels the other way: `LangGraphAgentRunner.stream` writes it into
    the input state on every turn, and the supervisor + specialist nodes read it back to
    append `build_locale_instruction(locale)` to their system prompts. It rides in the state
    rather than in the graph `config` because both node kinds already take `state` and
    nothing else needs it. `NotRequired` because a checkpointed thread written before this
    field existed replays without it — nodes fall back to the English-authored personas
    alone, which is exactly the old behavior rather than a crash.
    """

    route: NotRequired[str]
    locale: NotRequired[str]
