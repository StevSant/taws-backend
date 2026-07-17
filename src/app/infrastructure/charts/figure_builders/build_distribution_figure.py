from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.build_base_figure import build_base_figure
from app.infrastructure.charts.chart_image_style import ChartImageStyle

_MAX_TICKS = 8


def build_distribution_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a histogram of daily returns as vertical bars (x = return bucket, y = count)."""
    figure, axes = build_base_figure(style)
    series = spec.series[0] if spec.series else None
    points = series.points if series else []
    labels = [point.x for point in points]
    counts = [point.y for point in points]
    positions = range(len(counts))
    axes.bar(positions, counts, color=style.accent_color, width=0.9)
    if labels:
        step = max(1, len(labels) // _MAX_TICKS)
        tick_positions = list(range(0, len(labels), step))
        axes.set_xticks(tick_positions)
        axes.set_xticklabels([labels[index] for index in tick_positions], rotation=0)
    axes.set_xlabel(spec.x_axis.label)
    axes.set_ylabel(spec.y_axis.label)
    return figure
