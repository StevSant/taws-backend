from dataclasses import dataclass

from app.domain.agents.entities.tool_call import ToolCall


@dataclass(frozen=True, slots=True)
class ToolCallEvent:
    """A tool start/done hop, as yielded by `AgentRunner.stream`."""

    tool: ToolCall
