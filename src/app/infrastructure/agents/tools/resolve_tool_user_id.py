from langchain_core.runnables import RunnableConfig

from app.infrastructure.agents.user_id_config_key import USER_ID_CONFIG_KEY


def resolve_tool_user_id(config: RunnableConfig | None) -> str | None:
    """Return the authenticated user's id for this tool call, or `None` outside a graph run.

    SECURITY: the id comes from the verified JWT via `LangGraphAgentRunner.stream`'s
    `configurable` — NEVER from model-supplied tool arguments (the parameter is
    `RunnableConfig`-annotated, so it stays out of the args schema the model sees; same
    mechanism as `resolve_tool_locale`). A per-user tool that gets `None` back is running
    outside an authenticated chat turn (unit tests, direct calls) and must degrade to a
    "no user context" reply rather than guessing an id.
    """
    if config is not None:
        user_id = (config.get("configurable") or {}).get(USER_ID_CONFIG_KEY)
        if isinstance(user_id, str) and user_id:
            return user_id
    return None
