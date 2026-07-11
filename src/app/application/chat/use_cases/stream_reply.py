from collections.abc import AsyncIterator

from app.domain.agents.entities import AgentStreamEvent, Message
from app.domain.agents.ports import AgentRunner


class StreamReply:
    """Streams an assistant reply as `AgentStreamEvent`s via the agent layer.

    Depends only on the `AgentRunner` port — the application layer knows nothing
    about LangGraph or any specific graph shape. Per-thread history is the
    `AgentRunner`'s (checkpointer's) job now, keyed by `thread_id`; this use case no
    longer persists messages itself.
    """

    def __init__(self, agent_runner: AgentRunner) -> None:
        self._agent_runner = agent_runner

    async def execute(
        self, thread_id: str, message: Message, user_id: str
    ) -> AsyncIterator[AgentStreamEvent]:
        async for event in self._agent_runner.stream(thread_id, message, user_id):
            yield event
