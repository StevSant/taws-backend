"""Regression tests for the parallel tool-calling loop in `invoke_with_bound_tools`.

A round's tool calls run concurrently via `asyncio.gather`, so these lock in the invariants
that concurrency must not disturb: ToolMessage / evidence append order equals `tool_calls`
order, unknown-tool output is excluded from evidence, and each tool still emits its
START/DONE stream frame.
"""

import importlib
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, tool

from app.domain.agents.entities import ToolCallEventKind
from app.infrastructure.agents.invoke_with_bound_tools import invoke_with_bound_tools

# The package __init__ re-exports the `invoke_with_bound_tools` FUNCTION under the same name as
# its module, shadowing the submodule attribute — so `import ... as` would bind the function.
# Fetch the real module object from the import system to monkeypatch its `get_stream_writer`.
_invoke_module = importlib.import_module("app.infrastructure.agents.invoke_with_bound_tools")


@tool
async def alpha(x: str) -> str:
    """Echo an alpha result."""
    return f"alpha:{x}"


@tool
async def beta(x: str) -> str:
    """Echo a beta result."""
    return f"beta:{x}"


class _ToolsThenAnswerModel:
    """Bound-model stand-in: the first call requests `tool_calls`, the second answers."""

    def __init__(self, tool_calls: list[dict[str, Any]]) -> None:
        self._tool_calls = tool_calls
        self.calls = 0

    def bind_tools(self, tools: list[BaseTool]) -> "_ToolsThenAnswerModel":
        return self

    async def ainvoke(self, messages: list[BaseMessage], config: dict[str, Any]) -> AIMessage:
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=self._tool_calls)
        return AIMessage(content="final answer")


def _call(name: str, arg: str, call_id: str) -> dict[str, Any]:
    return {"name": name, "args": {"x": arg}, "id": call_id, "type": "tool_call"}


async def test_parallel_tool_calls_preserve_append_order_for_evidence() -> None:
    model = _ToolsThenAnswerModel([_call("alpha", "1", "call-a"), _call("beta", "2", "call-b")])
    evidence: list[BaseMessage] = []

    response = await invoke_with_bound_tools(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="hi")],
        [alpha, beta],
        evidence_messages=evidence,
    )

    assert response.content == "final answer"
    # gather preserves input order, so evidence follows the tool_calls order exactly.
    assert [str(m.content) for m in evidence] == ["alpha:1", "beta:2"]
    assert [getattr(m, "tool_call_id", None) for m in evidence] == ["call-a", "call-b"]


async def test_unknown_tool_output_is_not_recorded_as_evidence() -> None:
    model = _ToolsThenAnswerModel([_call("alpha", "1", "call-a"), _call("ghost", "9", "call-g")])
    evidence: list[BaseMessage] = []

    response = await invoke_with_bound_tools(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="hi")],
        [alpha, beta],
        evidence_messages=evidence,
    )

    assert response.content == "final answer"
    # Only the real tool's output is evidence; the unknown-tool placeholder is not.
    assert [str(m.content) for m in evidence] == ["alpha:1"]


async def test_each_tool_emits_one_start_and_one_done_frame(monkeypatch: Any) -> None:
    frames: list[dict[str, Any]] = []
    monkeypatch.setattr(_invoke_module, "get_stream_writer", lambda: frames.append)
    model = _ToolsThenAnswerModel([_call("alpha", "1", "call-a"), _call("beta", "2", "call-b")])

    await invoke_with_bound_tools(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="hi")],
        [alpha, beta],
        agent_name="advisor",
    )

    events = [(f["name"], f["event"]) for f in frames]
    for name in ("alpha", "beta"):
        assert events.count((name, ToolCallEventKind.START.value)) == 1
        assert events.count((name, ToolCallEventKind.DONE.value)) == 1
