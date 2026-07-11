SUPERVISOR_ROUTING_TAG = "supervisor_routing"
"""LangChain run tag marking the supervisor's structured-output routing call.

Set on the `config` passed to `model.with_structured_output(RouteDecision).ainvoke(...)`
in `supervisor_router_node.py`. `LangGraphAgentRunner.stream` checks for this tag on the
`(message_chunk, metadata)` payload of `stream_mode="messages"` events and skips yielding
a `TokenEvent` for it — otherwise the supervisor's raw structured-output JSON (e.g.
`{"route": "...", "reason": "..."}`) would leak into the SSE token stream ahead of the
chosen specialist's real answer text.
"""
