from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.llm.fallback_chat_model import build_fallback_chat_model


def build_chat_model(settings: Settings, model: str) -> BaseChatModel:
    """Build the LangChain chat model used by agent graphs, on the given `model`.

    THIS is the swap point for LLM providers inside agent graphs (as opposed to
    `LLMProvider`/`OpenAIProvider`, which back plain non-agent completions): agent
    graphs (`infrastructure/agents/chat_graph.py`) and `LangGraphAgentRunner` only
    depend on LangChain's `BaseChatModel` interface, so moving an agent graph to a
    different vendor (Anthropic, Gemini, ...) means changing what this function
    returns — nothing else in `infrastructure/agents/` needs to change.

    `model` is passed in rather than read off `settings` here (issue #28): the supervisor
    router and the 6 specialists now run on different tiers — `settings.openai_model` for
    the router's pure structured routing decision, `settings.reasoning_model` for the
    tool-calling specialists — and a factory that picked its own model couldn't serve both.
    `Container._get_router_chat_model` / `_get_specialist_chat_model` are the only callers,
    and both take the name from `Settings`, so no model string is ever hardcoded.

    Guarded like `OpenAIProvider`: without `settings.openai_api_key`, returns a
    fallback model that streams a placeholder reply instead of crashing, so agent
    graphs keep working before a real key is configured. This guard applies to BOTH tiers —
    the fallback is model-agnostic by construction.
    """
    if not settings.openai_api_key:
        return build_fallback_chat_model()

    return ChatOpenAI(model=model, api_key=SecretStr(settings.openai_api_key))
