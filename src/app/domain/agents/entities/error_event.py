from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """A terminal error, as yielded by `AgentRunner.stream` when the graph run fails.

    Adapters yield this instead of raising, so a failure mid-stream still reaches the
    SSE client as a well-formed frame instead of dropping the connection.
    """

    message: str
