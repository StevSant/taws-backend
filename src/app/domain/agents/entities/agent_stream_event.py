from app.domain.agents.entities.chart_event import ChartEvent
from app.domain.agents.entities.error_event import ErrorEvent
from app.domain.agents.entities.token_event import TokenEvent
from app.domain.agents.entities.trace_event import TraceEvent

AgentStreamEvent = TokenEvent | TraceEvent | ErrorEvent | ChartEvent
"""Discriminated union of everything `AgentRunner.stream` can yield for one turn.

Mirrors the SSE v2 wire protocol frame kinds 1:1 (`{"t": ...}` / `{"trace": ...}` /
`{"error": ...}` / `{"chart": ...}`), so `api/v1/routers/chat.py` only has to pattern-match
this union to serialize a frame — it never needs to know about LangGraph stream modes or
payloads.
"""
