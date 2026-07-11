from dataclasses import dataclass

from app.domain.agents.entities.agent_trace_event import AgentTraceEvent


@dataclass(frozen=True, slots=True)
class AgentTrace:
    """A single hop in the Supervisor's routing trace (e.g. "Supervisor -> Quant").

    `detail` is optional free text the emitting node may attach (routing reason,
    status note); `None` means the SSE frame omits the field entirely.
    """

    agent: str
    event: AgentTraceEvent
    detail: str | None = None
