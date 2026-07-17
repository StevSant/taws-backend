import asyncio
from collections.abc import Callable
from io import BytesIO

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.domain.charts.entities import ChartSpec, ChartType
from app.domain.charts.ports import ChartImageRenderer
from app.infrastructure.charts.chart_image_style import ChartImageStyle
from app.infrastructure.charts.figure_builders import (
    build_area_figure,
    build_bar_figure,
    build_candlestick_figure,
    build_comparison_figure,
    build_distribution_figure,
    build_drawdown_figure,
    build_gauge_figure,
    build_heatmap_figure,
    build_line_figure,
)

# Force the non-interactive Agg backend process-wide. We still use the object-oriented
# `Figure` + `FigureCanvasAgg` API (never `pyplot`), so no global figure registry is touched
# and rendering is safe to run concurrently under `asyncio.to_thread`.
matplotlib.use("Agg")

_FigureBuilder = Callable[[ChartSpec, ChartImageStyle], Figure]


class MatplotlibChartImageRenderer(ChartImageRenderer):
    """`ChartImageRenderer` adapter that rasterizes a `ChartSpec` to a PNG with matplotlib.

    The ONLY place in the codebase allowed to import matplotlib (hexagonal rule — vendor
    libraries stay out of `domain/`/`application/`). Dispatches on `spec.type` to one figure
    builder per type, stamps the title/subtitle and a `Source: …` footer, and encodes to PNG
    bytes in memory. The synchronous render runs under `asyncio.to_thread` so a chart never
    blocks the event loop. Raises (never returns partial bytes) on an unknown type or any
    render failure, so a caller can skip a single bad chart cleanly."""

    def __init__(self, style: ChartImageStyle) -> None:
        self._style = style
        self._builders: dict[ChartType, _FigureBuilder] = {
            ChartType.LINE: build_line_figure,
            ChartType.CANDLESTICK: build_candlestick_figure,
            ChartType.COMPARISON: build_comparison_figure,
            ChartType.AREA: build_area_figure,
            ChartType.DISTRIBUTION: build_distribution_figure,
            ChartType.DRAWDOWN: build_drawdown_figure,
            ChartType.GAUGE: build_gauge_figure,
            ChartType.BAR: build_bar_figure,
            ChartType.HEATMAP: build_heatmap_figure,
        }

    async def render(self, spec: ChartSpec) -> bytes:
        return await asyncio.to_thread(self._render_sync, spec)

    def _render_sync(self, spec: ChartSpec) -> bytes:
        builder = self._builders.get(spec.type)
        if builder is None:
            raise ValueError(f"No figure builder for chart type {spec.type!r}")
        figure = builder(spec, self._style)
        self._stamp_metadata(figure, spec)
        FigureCanvasAgg(figure)
        buffer = BytesIO()
        figure.savefig(
            buffer,
            format="png",
            dpi=self._style.dpi,
            facecolor=self._style.background_color,
            bbox_inches="tight",
        )
        return buffer.getvalue()

    def _stamp_metadata(self, figure: Figure, spec: ChartSpec) -> None:
        title = spec.meta.title
        if spec.meta.subtitle:
            title = f"{title}\n{spec.meta.subtitle}"
        figure.suptitle(title, color=self._style.text_color, fontsize=13, fontweight="bold")
        if spec.meta.source:
            figure.text(
                0.99,
                0.01,
                f"Source: {spec.meta.source}",
                ha="right",
                va="bottom",
                fontsize=8,
                color=self._style.text_color,
                alpha=0.7,
            )
