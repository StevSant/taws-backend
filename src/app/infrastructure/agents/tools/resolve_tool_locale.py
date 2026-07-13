from langchain_core.runnables import RunnableConfig

from app.infrastructure.agents.locale_config_key import LOCALE_CONFIG_KEY


def resolve_tool_locale(config: RunnableConfig | None, default_locale: str) -> str:
    """Return the locale for this tool call: the turn's locale, else `default_locale`.

    Every locale-aware chat tool declares a `config: RunnableConfig` parameter — LangChain
    injects the ambient config into it and, because the parameter is `RunnableConfig`-annotated,
    keeps it out of the tool's args schema, so the model never sees it and can't hallucinate a
    language. The value lands there via `LangGraphAgentRunner.stream`, which puts the resolved
    locale in the graph run's `configurable` under `LOCALE_CONFIG_KEY` (see that constant's
    comment for why the config, and not `SupervisorState`, is the channel that reaches a tool).

    `default_locale` remains as the fallback rather than being deleted, and is what the tool
    uses whenever there is no per-turn locale to read:
    - the Telegram/scheduled paths, which have no request to resolve a locale from;
    - a tool invoked outside a LangGraph run (unit tests, direct calls), where there is no
      ambient config at all.

    This is what un-freezes the tools: `default_locale` used to be captured at container build
    and baked into every call, so a Spanish user's chat-initiated signal/sentiment/scenario was
    generated — and, worse, *cached under* — the server's default locale no matter what they
    asked in.
    """
    if config is not None:
        locale = (config.get("configurable") or {}).get(LOCALE_CONFIG_KEY)
        if isinstance(locale, str) and locale:
            return locale
    return default_locale
