from dataclasses import dataclass, field

from app.domain.charts.entities.chart_request_kind import ChartRequestKind


@dataclass(frozen=True, slots=True)
class ChartRequest:
    """The parameters that produced a chart, echoed into `ChartMeta` so the frontend can
    re-issue it for another timeframe. `symbols` is generic — builders interpret it (one
    symbol for price, several for comparison, a macro series key for macro).

    `from_date`/`to_date` (ISO `YYYY-MM-DD`) carry an optional custom date range; when set
    they take precedence over `timeframe` and the series is sliced to that inclusive
    window. Kept as strings so the value object stays a plain wire-shaped echo."""

    kind: ChartRequestKind
    symbols: list[str] = field(default_factory=list)
    timeframe: str = ""
    from_date: str | None = None
    to_date: str | None = None
