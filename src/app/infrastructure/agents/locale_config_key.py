# The `configurable` key under which `LangGraphAgentRunner.stream` publishes the turn's
# resolved locale, and which the chat tools read back out of their injected `RunnableConfig`
# (see `infrastructure/agents/tools/resolve_tool_locale.py`).
#
# Locale travels to the *nodes* in `SupervisorState` and to the *tools* in the graph config.
# The split isn't arbitrary: a tool is invoked by `invoke_with_bound_tools` from inside a node,
# not by the graph, so it never receives the state — but LangChain injects the ambient
# `RunnableConfig` into any tool coroutine that declares a `RunnableConfig`-annotated
# parameter, and LangGraph makes the run's `configurable` ambient for the whole node. That is
# the only channel that reaches a tool without either threading an extra argument through
# every tool signature (which the model would then see in the args schema and try to fill in
# itself) or moving to a `ToolNode` + `InjectedState`, which would change the graph's shape.
LOCALE_CONFIG_KEY = "locale"
