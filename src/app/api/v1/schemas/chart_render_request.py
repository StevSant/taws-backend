from pydantic import BaseModel, Field

from app.domain.charts.entities import ChartRequestKind


class ChartRenderRequest(BaseModel):
    """Request body for `POST /api/v1/charts/render` — re-render a chart at a new timeframe."""

    kind: ChartRequestKind
    symbols: list[str] = Field(default_factory=list, max_length=8)
    timeframe: str = Field(default="", max_length=10)
