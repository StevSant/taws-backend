from dataclasses import dataclass, field

from app.domain.charts.entities.chart_request import ChartRequest


@dataclass(frozen=True, slots=True)
class ChartMeta:
    """Presentation + re-request metadata for a chart. `timeframes` (available options)
    comes from config, so the frontend never hardcodes timeframe buttons."""

    title: str
    source: str
    timeframe: str
    request: ChartRequest
    timeframes: list[str] = field(default_factory=list)
    subtitle: str | None = None
    symbol: str | None = None
