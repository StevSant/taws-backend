from typing import NotRequired

from langgraph.graph import MessagesState


class SupervisorState(MessagesState):
    """Graph state for `build_supervisor_graph`: `MessagesState` plus the chosen route.

    `route` is written by the supervisor node (see `supervisor_router_node.py`) and
    read by `select_specialist_route` to pick the conditional edge; it's absent from
    the initial input state (`NotRequired`), which is why it can't be a plain `str`.

    `grounding_context` (issue #73) is an optional pre-formatted string describing one
    specific asset or news article the user referenced; when present, the specialist node
    prepends it as a `SystemMessage` to anchor its reply (see `specialist_node_factory`).
    It's supplied on the initial input state (or omitted), hence `NotRequired`.
    """

    route: NotRequired[str]
    grounding_context: NotRequired[str]
