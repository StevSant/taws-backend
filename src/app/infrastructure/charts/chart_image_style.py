from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartImageStyle:
    """Geometry + on-brand palette for the matplotlib PNG renderer, assembled from `Settings`.

    Injected into `MatplotlibChartImageRenderer` and every figure builder so no size or color
    is hardcoded in rendering code (CLAUDE.md's no-hardcoded-values rule). `width_px`/
    `height_px`/`dpi` map to matplotlib's `figsize` = (width_px / dpi, height_px / dpi); the
    colors are the dark/gold theme the web chat uses, so a Telegram image reads as the same
    product as the browser."""

    width_px: int
    height_px: int
    dpi: int
    background_color: str
    text_color: str
    grid_color: str
    accent_color: str
    up_color: str
    down_color: str

    @property
    def figsize_inches(self) -> tuple[float, float]:
        """matplotlib `figsize`, in inches, derived from the pixel geometry and DPI."""
        return (self.width_px / self.dpi, self.height_px / self.dpi)
