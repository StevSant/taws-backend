from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.build_base_figure import build_base_figure
from app.infrastructure.charts.chart_image_style import ChartImageStyle
from app.infrastructure.charts.format_time_axis import format_time_axis

# Distinct line colors for overlaid series (gold accent first, then a readable spread).
_SERIES_COLORS = ("#d4af37", "#4da3ff", "#16c784", "#ea3943", "#b892ff", "#ff9f40")


def build_comparison_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a multi-series comparison chart (each series rebased to 100) with a legend."""
    figure, axes = build_base_figure(style)
    longest_x: list[str] = []
    for index, series in enumerate(spec.series):
        y_values = [point.y for point in series.points]
        axes.plot(
            range(len(y_values)),
            y_values,
            color=_SERIES_COLORS[index % len(_SERIES_COLORS)],
            linewidth=1.6,
            label=series.name,
        )
        if len(series.points) > len(longest_x):
            longest_x = [point.x for point in series.points]
    axes.set_xlabel(spec.x_axis.label)
    axes.set_ylabel(spec.y_axis.label)
    format_time_axis(axes, longest_x)
    if spec.series:
        legend = axes.legend(
            loc="best", facecolor=style.background_color, edgecolor=style.grid_color
        )
        for text in legend.get_texts():
            text.set_color(style.text_color)
    return figure
