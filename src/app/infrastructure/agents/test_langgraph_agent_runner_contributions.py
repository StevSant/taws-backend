"""Runner test: a `custom` frame with `kind == "contributions"` becomes a `ContributionsEvent`.

Mirrors `test_langgraph_agent_runner_citations.py` — covers the second half of the multi-specialist
stance frame's path (custom-stream dict -> typed domain event), the counterpart to the SSE
serialization covered by `api/v1/routers/test_chat_to_sse_frame_contributions.py`.
"""

from collections.abc import AsyncIterator
from typing import Any

from app.domain.agents.entities import ContributionsEvent, Message, MessageRole
from app.infrastructure.agents import LangGraphAgentRunner


class _FakeGraph:
    async def astream(
        self,
        input_state: dict[str, Any],
        config: dict[str, Any],
        stream_mode: list[str],
    ) -> AsyncIterator[tuple[str, Any]]:
        yield (
            "custom",
            {
                "kind": "contributions",
                "contributions": [
                    {"agent": "quant", "stance": "bull", "confidence": 0.7, "headline": "Up"},
                    {"agent": "macro", "stance": "neutral", "confidence": 0.0, "headline": ""},
                ],
            },
        )


async def test_runner_converts_contributions_custom_frame() -> None:
    runner = LangGraphAgentRunner(_FakeGraph())

    events = [
        event
        async for event in runner.stream(
            "thread",
            Message(role=MessageRole.USER, content="compare"),
            "user",
            "es",
        )
    ]

    contribution_events = [event for event in events if isinstance(event, ContributionsEvent)]
    assert len(contribution_events) == 1
    assert contribution_events[0].contributions[0] == {
        "agent": "quant",
        "stance": "bull",
        "confidence": 0.7,
        "headline": "Up",
    }
