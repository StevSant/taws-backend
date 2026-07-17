from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.build_base_figure import build_base_figure
from app.infrastructure.charts.chart_image_style import ChartImageStyle
from app.infrastructure.charts.format_time_axis import format_time_axis


def build_drawdown_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a drawdown curve (decline from the running peak, values <= 0) filled downward."""
    figure, axes = build_base_figure(style)
    series = spec.series[0] if spec.series else None
    points = series.points if series else []
    y_values = [point.y for point in points]
    x_positions = range(len(y_values))
    axes.plot(x_positions, y_values, color=style.down_color, linewidth=1.4)
    axes.fill_between(x_positions, y_values, 0.0, color=style.down_color, alpha=0.25)
    axes.axhline(0.0, color=style.grid_color, linewidth=0.8)
    axes.set_xlabel(spec.x_axis.label)
    axes.set_ylabel(spec.y_axis.label)
    format_time_axis(axes, [point.x for point in points])
    return figure
