from app.domain.charts.entities import (
    ChartAxis,
    ChartConfig,
    ChartMeta,
    ChartPoint,
    ChartRequest,
    ChartRequestKind,
    ChartSeries,
    ChartSpec,
    ChartType,
)
from app.domain.sentiment.ports import FearGreedProvider


class BuildSentimentGauge:
    """Build a 0-100 gauge of the current Crypto Fear & Greed Index.

    Calls `FearGreedProvider.get_fear_greed_index()` which returns a `FearGreedReading`
    (value: int 0-100, classification: FearGreedClassification StrEnum, as_of: datetime).
    The classification string (e.g. "extreme_fear", "greed") is used as the x-axis label
    so the frontend can annotate the gauge needle position.

    `ChartConfig` is injected for DI uniformity across all chart use cases but is not
    used in gauge logic — a gauge is always a single current value, never time-windowed.
    """

    def __init__(self, fear_greed_provider: FearGreedProvider, chart_config: ChartConfig) -> None:
        self._fear_greed_provider = fear_greed_provider
        self._chart_config = chart_config

    async def execute(self) -> ChartSpec:
        reading = await self._fear_greed_provider.get_fear_greed_index()
        value = float(reading.value)
        classification = reading.classification.value  # StrEnum — .value gives the string

        return ChartSpec(
            type=ChartType.GAUGE,
            series=[
                ChartSeries(
                    name="Fear & Greed",
                    points=[ChartPoint(x=classification, y=value)],
                )
            ],
            x_axis=ChartAxis(label="", type="value"),
            y_axis=ChartAxis(label="", type="value"),
            meta=ChartMeta(
                title=f"Fear & Greed: {classification.replace('_', ' ').title()} ({value:.0f})",
                source="alternative.me",
                timeframe="",
                timeframes=[],
                request=ChartRequest(
                    kind=ChartRequestKind.SENTIMENT_GAUGE, symbols=[], timeframe=""
                ),
            ),
        )
