from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """A single assistant token, as yielded by `AgentRunner.stream`."""

    token: str
