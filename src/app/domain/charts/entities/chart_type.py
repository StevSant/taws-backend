from enum import StrEnum


class ChartType(StrEnum):
    """Visual family of a chart. Library-agnostic — the frontend maps each to an
    ECharts option; the backend never names ECharts concepts."""

    LINE = "line"
    CANDLESTICK = "candlestick"
    COMPARISON = "comparison"
    AREA = "area"
    DISTRIBUTION = "distribution"
    DRAWDOWN = "drawdown"
    GAUGE = "gauge"
    BAR = "bar"
    HEATMAP = "heatmap"
