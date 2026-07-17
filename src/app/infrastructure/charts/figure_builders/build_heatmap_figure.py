import math

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec
from app.infrastructure.charts.chart_image_style import ChartImageStyle

_MIN_SPAN = 1.0  # floor for the symmetric color scale so tiny moves still show some hue


def build_heatmap_figure(spec: ChartSpec, style: ChartImageStyle) -> Figure:
    """Render a watchlist heatmap: a grid of labelled tiles colored by value (red<0<green).

    Reads `spec.cells` (`[{label, value}]`), lays them out in a near-square grid, and colors
    each tile on a diverging scale symmetric around zero so gains read green and losses red."""
    figure = Figure(figsize=style.figsize_inches, dpi=style.dpi, facecolor=style.background_color)
    axes = figure.add_subplot(111)
    axes.set_facecolor(style.background_color)
    axes.axis("off")

    cells = spec.cells or []
    if not cells:
        return figure

    columns = max(1, math.ceil(math.sqrt(len(cells))))
    rows = math.ceil(len(cells) / columns)
    grid = np.full((rows, columns), np.nan)
    for index, cell in enumerate(cells):
        grid[index // columns][index % columns] = cell.value

    span = max(_MIN_SPAN, float(np.nanmax(np.abs(grid))))
    colormap = _diverging_colormap(style)
    colormap.set_bad(style.background_color)
    axes.imshow(grid, cmap=colormap, vmin=-span, vmax=span, aspect="auto")

    for index, cell in enumerate(cells):
        row, column = index // columns, index % columns
        axes.text(
            column,
            row,
            f"{cell.label}\n{cell.value:+.2f}%",
            ha="center",
            va="center",
            fontsize=11,
            color="#0e1116",
            fontweight="bold",
        )
    return figure


def _diverging_colormap(style: ChartImageStyle) -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(
        "watchlist", [style.down_color, "#f5f5f5", style.up_color]
    )
