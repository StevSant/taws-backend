from typing import Annotated

from fastapi import Depends

from app.application.signals.use_cases import ForceAnalyzeNewsItem
from app.core.di import Container, get_container


def get_force_analyze_news_item_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> ForceAnalyzeNewsItem:
    """FastAPI dependency resolving the manual "Analizar ahora" pipeline (issue #27).

    It calls `GenerateSignal` with `force=True` — see `ForceAnalyzeNewsItem`'s docstring for
    why the freshness cache must be bypassed there specifically.
    """
    return container.get_force_analyze_news_item_use_case()
