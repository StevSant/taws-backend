from app.application.charts.use_cases.build_comparison_chart import BuildComparisonChart
from app.application.charts.use_cases.build_distribution_chart import BuildDistributionChart
from app.application.charts.use_cases.build_drawdown_chart import BuildDrawdownChart
from app.application.charts.use_cases.build_macro_chart import BuildMacroChart
from app.application.charts.use_cases.build_price_chart import BuildPriceChart
from app.application.charts.use_cases.build_sentiment_gauge import BuildSentimentGauge
from app.domain.charts.entities import ChartRequestKind, ChartSpec, ChartType


class RenderChart:
    """Dispatch a `ChartRequest` (kind + symbols + timeframe) to the matching builder.

    This is the user-triggered path (timeframe toggles via `POST /charts/render`) — it
    reuses the exact same builders the LLM tools use, so a re-rendered chart is identical
    to the streamed one, just at a new timeframe."""

    def __init__(
        self,
        build_price_chart: BuildPriceChart,
        build_comparison_chart: BuildComparisonChart,
        build_drawdown_chart: BuildDrawdownChart,
        build_distribution_chart: BuildDistributionChart,
        build_macro_chart: BuildMacroChart,
        build_sentiment_gauge: BuildSentimentGauge,
    ) -> None:
        self._build_price_chart = build_price_chart
        self._build_comparison_chart = build_comparison_chart
        self._build_drawdown_chart = build_drawdown_chart
        self._build_distribution_chart = build_distribution_chart
        self._build_macro_chart = build_macro_chart
        self._build_sentiment_gauge = build_sentiment_gauge

    async def execute(
        self, kind: ChartRequestKind, symbols: list[str], timeframe: str
    ) -> ChartSpec:
        first = symbols[0] if symbols else ""
        if kind is ChartRequestKind.PRICE_CANDLESTICK:
            return await self._build_price_chart.execute(first, timeframe, ChartType.CANDLESTICK)
        if kind is ChartRequestKind.PRICE_LINE:
            return await self._build_price_chart.execute(first, timeframe, ChartType.LINE)
        if kind is ChartRequestKind.COMPARISON:
            return await self._build_comparison_chart.execute(symbols, timeframe)
        if kind is ChartRequestKind.DRAWDOWN:
            return await self._build_drawdown_chart.execute(first, timeframe)
        if kind is ChartRequestKind.DISTRIBUTION:
            return await self._build_distribution_chart.execute(first, timeframe)
        if kind is ChartRequestKind.MACRO:
            return await self._build_macro_chart.execute(first, timeframe)
        return await self._build_sentiment_gauge.execute()
