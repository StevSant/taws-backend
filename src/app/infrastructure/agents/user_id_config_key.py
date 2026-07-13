# The `configurable` key under which `LangGraphAgentRunner.stream` publishes the
# authenticated caller's id, and which per-user chat tools read back out of their injected
# `RunnableConfig` (see `infrastructure/agents/tools/resolve_tool_user_id.py`).
#
# Same channel rationale as `LOCALE_CONFIG_KEY` (see `locale_config_key.py`): the config is
# the only value that reaches a tool without surfacing an argument in the model-visible args
# schema. That invisibility is load-bearing here — the id comes from the verified JWT, and a
# model-supplied `user_id` argument would let a prompt request another tenant's data.
USER_ID_CONFIG_KEY = "user_id"
