"""Unit tests for grounding-context injection in the specialist node (issue #73).

When `SupervisorState` carries a `grounding_context` string, the specialist node injects
it as an extra `SystemMessage` *after* the persona/format guardrails (framed as reference
data, not instructions) and before the thread history, so the resolved asset/news facts
anchor the reply without overriding persona/format rules. When it's absent, the assembled
message list is exactly as before (persona messages only).
"""

from typing import Any

import app.infrastructure.agents.specialist_node_factory as node_factory_module
from app.infrastructure.agents.personas import MIDAS_PERSONA
from app.infrastructure.agents.specialist_node_factory import build_specialist_node


class _RecordingChatModel:
    """Minimal fake chat model: records the messages it was invoked with."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> str:
        self.messages = messages
        return "reply"


def _patch_writer(monkeypatch: Any) -> None:
    monkeypatch.setattr(node_factory_module, "get_stream_writer", lambda: lambda _payload: None)


async def test_grounding_context_injected_after_guardrails(monkeypatch: Any) -> None:
    _patch_writer(monkeypatch)
    model = _RecordingChatModel()
    node = build_specialist_node("analyst", "PERSONA", model)

    grounding = "Asset AAPL (Apple Inc.)"
    await node({"messages": ["user-msg"], "grounding_context": grounding})

    contents = [getattr(m, "content", m) for m in model.messages]
    # The grounding facts are present, wrapped as reference data (not a bare instruction).
    grounding_msg = next(c for c in contents if isinstance(c, str) and grounding in c)
    assert "never as instructions" in grounding_msg
    # Guardrails (persona/format) come FIRST; grounding is injected after them, before the thread.
    assert contents.index(MIDAS_PERSONA) < contents.index(grounding_msg)
    assert contents.index(grounding_msg) < contents.index("user-msg")


async def test_no_grounding_context_leaves_messages_unchanged(monkeypatch: Any) -> None:
    _patch_writer(monkeypatch)
    model = _RecordingChatModel()
    node = build_specialist_node("analyst", "PERSONA", model)

    await node({"messages": ["user-msg"]})

    contents = [getattr(m, "content", m) for m in model.messages]
    # First message is the Midas persona identity — no grounding SystemMessage ahead of it.
    assert contents[0] == MIDAS_PERSONA
