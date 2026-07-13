from typing import Annotated

from fastapi import Depends

from app.application.signals.use_cases import AnalyzePendingNews
from app.core.di import Container, get_container


def get_analyze_pending_news_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> AnalyzePendingNews:
    """FastAPI dependency resolving the pending-news batch pipeline — same "resolve the use
    case, not its ports" rationale as `get_generate_signal_use_case`."""
    return container.get_analyze_pending_news_use_case()
