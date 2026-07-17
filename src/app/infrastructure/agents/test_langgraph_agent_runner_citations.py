from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessageChunk

from app.domain.agents.entities import CitationsEvent, Message, MessageRole, TokenEvent
from app.infrastructure.agents import INTERNAL_CONTRIBUTOR_TAG, LangGraphAgentRunner


class _FakeGraph:
    async def astream(
        self,
        input_state: dict[str, Any],
        config: dict[str, Any],
        stream_mode: list[str],
    ) -> AsyncIterator[tuple[str, Any]]:
        yield (
            "messages",
            (
                AIMessageChunk(content="hidden"),
                {"tags": [INTERNAL_CONTRIBUTOR_TAG]},
            ),
        )
        yield "messages", (AIMessageChunk(content="visible"), {"tags": []})
        yield (
            "custom",
            {
                "kind": "citations",
                "citations": [
                    {
                        "kind": "quant",
                        "claim": "Computed return",
                        "metric": "return",
                        "value": "-33%",
                    }
                ],
            },
        )


async def test_runner_hides_contributor_tokens_and_yields_citations() -> None:
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

    assert [event.token for event in events if isinstance(event, TokenEvent)] == ["visible"]
    citation_events = [event for event in events if isinstance(event, CitationsEvent)]
    assert citation_events[0].citations[0]["value"] == "-33%"
