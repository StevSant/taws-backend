from matplotlib.figure import Figure
from matplotlib.patches import Wedge

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.chart_image_style import ChartImageStyle

_GAUGE_MIN = 0.0
_GAUGE_MAX = 100.0


def build_gauge_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a 0-100 semicircular gauge (e.g. the Fear & Greed index) as a matplotlib Figure.

    The filled arc runs from the left (0) up to the current value, colored from red (fear)
    through gold to green (greed); the numeric value sits in the center."""
    figure = Figure(figsize=style.figsize_inches, dpi=style.dpi, facecolor=style.background_color)
    axes = figure.add_subplot(111)
    axes.set_facecolor(style.background_color)
    axes.set_xlim(-1.2, 1.2)
    axes.set_ylim(-0.3, 1.2)
    axes.set_aspect("equal")
    axes.axis("off")

    value = _gauge_value(spec)
    fraction = max(0.0, min(1.0, (value - _GAUGE_MIN) / (_GAUGE_MAX - _GAUGE_MIN)))
    # Semicircle: 180deg (left) -> 0deg (right). The filled sweep grows clockwise from 180.
    filled_end = 180.0 - fraction * 180.0
    axes.add_patch(Wedge((0, 0), 1.0, 0, 180, width=0.3, facecolor=style.grid_color))
    axes.add_patch(
        Wedge((0, 0), 1.0, filled_end, 180, width=0.3, facecolor=_zone_color(fraction, style))
    )
    axes.text(
        0,
        0.15,
        f"{value:.0f}",
        ha="center",
        va="center",
        fontsize=32,
        color=style.text_color,
        fontweight="bold",
    )
    return figure


def _gauge_value(spec: ChartSpec) -> float:
    series = spec.series[0] if spec.series else None
    if series and series.points:
        return series.points[0].y
    return 0.0


def _zone_color(fraction: float, style: ChartImageStyle) -> str:
    """Red for fear (low), gold in the middle, green for greed (high)."""
    if fraction < 0.4:
        return style.down_color
    if fraction < 0.6:
        return style.accent_color
    return style.up_color
