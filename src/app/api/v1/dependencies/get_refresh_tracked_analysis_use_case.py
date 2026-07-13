from typing import Annotated

from fastapi import Depends

from app.application.analysis.use_cases import RefreshTrackedAnalysis
from app.core.di import Container, get_container


def get_refresh_tracked_analysis_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> RefreshTrackedAnalysis:
    """FastAPI dependency resolving the background-refresh use case (issue #29).

    Backs `POST /api/v1/analysis/refresh` and the watchlist-add seed. The scheduler's tick runs
    the exact same instance.
    """
    return container.get_refresh_tracked_analysis_use_case()
