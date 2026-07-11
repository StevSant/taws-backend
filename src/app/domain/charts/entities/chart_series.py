from dataclasses import dataclass, field

from app.domain.charts.entities.chart_point import ChartPoint
from app.domain.charts.entities.ohlc_bar import OhlcBar


@dataclass(frozen=True, slots=True)
class ChartSeries:
    """One named series. Exactly one of `points`/`bars` is populated depending on the
    owning `ChartSpec.type` (bars for candlestick, points for everything else)."""

    name: str
    points: list[ChartPoint] = field(default_factory=list)
    bars: list[OhlcBar] = field(default_factory=list)
