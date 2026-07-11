from typing import NotRequired

from langgraph.graph import MessagesState


class SupervisorState(MessagesState):
    """Graph state for `build_supervisor_graph`: `MessagesState` plus the chosen route.

    `route` is written by the supervisor node (see `supervisor_router_node.py`) and
    read by `select_specialist_route` to pick the conditional edge; it's absent from
    the initial input state (`NotRequired`), which is why it can't be a plain `str`.
    """

    route: NotRequired[str]
