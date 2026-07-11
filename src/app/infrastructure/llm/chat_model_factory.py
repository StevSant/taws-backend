from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.llm.fallback_chat_model import build_fallback_chat_model


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Build the LangChain chat model used by agent graphs.

    THIS is the swap point for LLM providers inside agent graphs (as opposed to
    `LLMProvider`/`OpenAIProvider`, which back plain non-agent completions): agent
    graphs (`infrastructure/agents/chat_graph.py`) and `LangGraphAgentRunner` only
    depend on LangChain's `BaseChatModel` interface, so moving an agent graph to a
    different vendor (Anthropic, Gemini, ...) means changing what this function
    returns — nothing else in `infrastructure/agents/` needs to change.

    Guarded like `OpenAIProvider`: without `settings.openai_api_key`, returns a
    fallback model that streams a placeholder reply instead of crashing, so agent
    graphs keep working before a real key is configured.
    """
    if not settings.openai_api_key:
        return build_fallback_chat_model()

    return ChatOpenAI(model=settings.openai_model, api_key=SecretStr(settings.openai_api_key))
