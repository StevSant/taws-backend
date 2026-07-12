from typing import Annotated

from fastapi import Depends

from app.application.charts.use_cases import RenderChart
from app.core.di import Container, get_container


def get_render_chart_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> RenderChart:
    """FastAPI dependency resolving the RenderChart dispatcher from the DI container."""
    return container.get_render_chart_use_case()
