from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.build_base_figure import build_base_figure
from app.infrastructure.charts.chart_image_style import ChartImageStyle
from app.infrastructure.charts.format_time_axis import format_time_axis

_BODY_WIDTH = 0.6


def build_candlestick_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render an OHLC candlestick chart as a matplotlib Figure (up/down colored bodies)."""
    figure, axes = build_base_figure(style)
    series = spec.series[0] if spec.series else None
    bars = series.bars if series else []
    for index, bar in enumerate(bars):
        color = style.up_color if bar.c >= bar.o else style.down_color
        axes.vlines(index, bar.l, bar.h, color=color, linewidth=1.0)
        lower = min(bar.o, bar.c)
        height = abs(bar.c - bar.o) or (bar.h - bar.l) * 0.01 or 1e-9
        axes.add_patch(
            Rectangle(
                (index - _BODY_WIDTH / 2, lower),
                _BODY_WIDTH,
                height,
                facecolor=color,
                edgecolor=color,
            )
        )
    if bars:
        axes.set_xlim(-1, len(bars))
        lows = [bar.l for bar in bars]
        highs = [bar.h for bar in bars]
        axes.set_ylim(min(lows), max(highs))
    axes.set_xlabel(spec.x_axis.label)
    axes.set_ylabel(spec.y_axis.label)
    format_time_axis(axes, [bar.t for bar in bars])
    return figure
