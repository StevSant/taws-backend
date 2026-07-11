from enum import StrEnum


class ChartRequestKind(StrEnum):
    """What a chart re-request should rebuild. Stored in `ChartMeta.request.kind` so the
    frontend can re-issue the same chart for a different timeframe via `POST
    /charts/render`, and so `RenderChart` (the endpoint dispatcher) can pick a builder."""

    PRICE_CANDLESTICK = "price_candlestick"
    PRICE_LINE = "price_line"
    COMPARISON = "comparison"
    MACRO = "macro"
    DRAWDOWN = "drawdown"
    DISTRIBUTION = "distribution"
    SENTIMENT_GAUGE = "sentiment_gauge"
