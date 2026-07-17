from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.build_base_figure import build_base_figure
from app.infrastructure.charts.chart_image_style import ChartImageStyle
from app.infrastructure.charts.format_time_axis import format_time_axis


def build_area_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a single-series area chart (a filled line) as a matplotlib Figure."""
    figure, axes = build_base_figure(style)
    series = spec.series[0] if spec.series else None
    points = series.points if series else []
    y_values = [point.y for point in points]
    x_positions = range(len(y_values))
    axes.plot(x_positions, y_values, color=style.accent_color, linewidth=1.6)
    axes.fill_between(x_positions, y_values, color=style.accent_color, alpha=0.25)
    axes.set_xlabel(spec.x_axis.label)
    axes.set_ylabel(spec.y_axis.label)
    format_time_axis(axes, [point.x for point in points])
    return figure
