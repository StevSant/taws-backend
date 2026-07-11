from dataclasses import dataclass

from app.domain.agents.entities.agent_trace import AgentTrace


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """An `AgentTrace` hop, as yielded by `AgentRunner.stream`."""

    trace: AgentTrace
