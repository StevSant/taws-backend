from abc import ABC, abstractmethod

from app.domain.charts.entities import ChartSpec


class ChartImageRenderer(ABC):
    """Port that rasterizes a channel-agnostic `ChartSpec` into a PNG image.

    The web chat renders a `ChartSpec` client-side with ECharts, but channels that can only
    show an image (Telegram `sendPhoto`, and later email/alert snapshots) need the chart
    rendered server-side. This is that seam: an adapter turns the same `ChartSpec` the
    frontend consumes into PNG bytes, so both channels draw the identical data.

    `render` returns the complete PNG bytes or RAISES — it must never return partial/empty
    bytes on failure, so the caller (e.g. `ChatMessageHandler`) can wrap one chart's render
    in try/except and skip only that image without ever sending a corrupt one."""

    @abstractmethod
    async def render(self, spec: ChartSpec) -> bytes:
        """Render `spec` to PNG bytes. Raises on an unsupported type or a render failure."""
        raise NotImplementedError
