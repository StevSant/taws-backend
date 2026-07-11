from enum import StrEnum


class AgentTraceEvent(StrEnum):
    """Lifecycle event carried by an `AgentTrace` frame in the SSE v2 protocol.

    - `ROUTING`: the supervisor has picked a specialist for this turn.
    - `START`: a specialist has begun working on the turn.
    - `DONE`: a specialist has finished working on the turn.
    """

    ROUTING = "routing"
    START = "start"
    DONE = "done"
