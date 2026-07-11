from dataclasses import dataclass, field

from app.domain.charts.entities.chart_request_kind import ChartRequestKind


@dataclass(frozen=True, slots=True)
class ChartRequest:
    """The parameters that produced a chart, echoed into `ChartMeta` so the frontend can
    re-issue it for another timeframe. `symbols` is generic — builders interpret it (one
    symbol for price, several for comparison, a macro series key for macro)."""

    kind: ChartRequestKind
    symbols: list[str] = field(default_factory=list)
    timeframe: str = ""
