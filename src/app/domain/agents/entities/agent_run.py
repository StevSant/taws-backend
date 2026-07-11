from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.agents.entities.agent_run_status import AgentRunStatus


@dataclass(slots=True)
class AgentRun:
    """A single execution of an agent graph for a given thread."""

    id: str
    thread_id: str
    status: AgentRunStatus = AgentRunStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
