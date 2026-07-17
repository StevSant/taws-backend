from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.build_base_figure import build_base_figure
from app.infrastructure.charts.chart_image_style import ChartImageStyle


def build_bar_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a categorical bar chart (x = symbol, y = % change), colored by sign of y.

    Used by the market-movers chart: green bars for gainers, red for losers."""
    figure, axes = build_base_figure(style)
    series = spec.series[0] if spec.series else None
    points = series.points if series else []
    labels = [point.x for point in points]
    values = [point.y for point in points]
    colors = [style.up_color if value >= 0 else style.down_color for value in values]
    positions = range(len(values))
    axes.bar(positions, values, color=colors, width=0.7)
    axes.axhline(0.0, color=style.grid_color, linewidth=0.8)
    axes.set_xticks(list(positions))
    axes.set_xticklabels(labels, rotation=45, ha="right")
    axes.set_xlabel(spec.x_axis.label)
    axes.set_ylabel(spec.y_axis.label)
    return figure
