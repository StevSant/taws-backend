from typing import Annotated

from fastapi import Depends
from langchain_core.language_models import BaseChatModel

from app.core.di import Container, get_container


def get_chat_model(container: Annotated[Container, Depends(get_container)]) -> BaseChatModel:
    """FastAPI dependency resolving the shared LangChain chat model from the DI container.

    Used by batch/structured pipelines (Analyst signal generation, Advisor briefing
    composition) that call `model.with_structured_output(...)` / `model.ainvoke(...)`
    directly, outside the chat/SSE `AgentRunner` graph.
    """
    return container.get_chat_model()
