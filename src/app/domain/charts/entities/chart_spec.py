from dataclasses import dataclass, field

from app.domain.charts.entities.chart_axis import ChartAxis
from app.domain.charts.entities.chart_meta import ChartMeta
from app.domain.charts.entities.chart_series import ChartSeries
from app.domain.charts.entities.chart_type import ChartType


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """A complete, library-agnostic chart description. Serialized to the camelCase wire
    dict by `serialize_chart_spec` and rendered by the Angular `<taws-chart>` adapter."""

    type: ChartType
    x_axis: ChartAxis
    y_axis: ChartAxis
    meta: ChartMeta
    series: list[ChartSeries] = field(default_factory=list)
