from matplotlib.axes import Axes
from matplotlib.figure import Figure

from app.infrastructure.charts.chart_image_style import ChartImageStyle


def build_base_figure(style: ChartImageStyle) -> tuple[Figure, Axes]:
    """Create a themed `Figure` + single `Axes` via matplotlib's object-oriented API.

    The ONE place figure geometry and axis theming live, so the nine figure builders never
    each re-apply the dark background, grid, spine, and tick colors. Uses `Figure(...)`
    directly (never `pyplot`, which is not thread-safe and keeps global state) so the
    renderer is safe to run under `asyncio.to_thread` per request."""
    figure = Figure(figsize=style.figsize_inches, dpi=style.dpi, facecolor=style.background_color)
    axes = figure.add_subplot(111)
    axes.set_facecolor(style.background_color)
    axes.tick_params(colors=style.text_color, labelsize=9)
    axes.grid(True, color=style.grid_color, linewidth=0.6, alpha=0.7)
    for spine in axes.spines.values():
        spine.set_color(style.grid_color)
    axes.xaxis.label.set_color(style.text_color)
    axes.yaxis.label.set_color(style.text_color)
    return figure, axes
