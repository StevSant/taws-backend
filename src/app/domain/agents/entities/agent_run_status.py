from enum import StrEnum


class AgentRunStatus(StrEnum):
    """Lifecycle state of a single agent run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
