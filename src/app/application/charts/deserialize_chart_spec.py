from typing import Any

from app.domain.charts.entities import (
    ChartAxis,
    ChartCell,
    ChartMeta,
    ChartPoint,
    ChartRequest,
    ChartRequestKind,
    ChartSeries,
    ChartSpec,
    ChartType,
    OhlcBar,
)


def deserialize_chart_spec(data: dict[str, Any]) -> ChartSpec:
    """Rebuild a `ChartSpec` from the camelCase wire dict `serialize_chart_spec` produced.

    The exact inverse of `serialize_chart_spec`, kept beside it so the two can't drift. It
    exists for the Telegram image path: charts reach `ChatMessageHandler` as already-
    serialized wire dicts (that is what `ChartEvent.chart` carries over the SSE custom
    channel), but the `ChartImageRenderer` port and its matplotlib figure builders work on
    the typed domain `ChartSpec`. This turns the dict back into that entity so the renderer
    never has to parse loosely-typed dicts. Unknown/absent keys fall back to safe defaults
    so a slightly older or newer wire dict never crashes the render."""
    cells_data = data.get("cells")
    return ChartSpec(
        type=ChartType(data["type"]),
        series=[_deserialize_series(series) for series in data.get("series", [])],
        x_axis=_deserialize_axis(data.get("xAxis", {})),
        y_axis=_deserialize_axis(data.get("yAxis", {})),
        meta=_deserialize_meta(data.get("meta", {})),
        cells=(
            [ChartCell(label=cell["label"], value=cell["value"]) for cell in cells_data]
            if cells_data is not None
            else None
        ),
    )


def _deserialize_axis(data: dict[str, Any]) -> ChartAxis:
    return ChartAxis(
        label=data.get("label", ""),
        type=data.get("type", "value"),
        format=data.get("format"),
    )


def _deserialize_series(data: dict[str, Any]) -> ChartSeries:
    return ChartSeries(
        name=data.get("name", ""),
        points=[ChartPoint(x=point["x"], y=point["y"]) for point in data.get("points", [])],
        bars=[
            OhlcBar(t=bar["t"], o=bar["o"], h=bar["h"], l=bar["l"], c=bar["c"], v=bar.get("v"))
            for bar in data.get("bars", [])
        ],
    )


def _deserialize_meta(data: dict[str, Any]) -> ChartMeta:
    request = data.get("request", {})
    return ChartMeta(
        title=data.get("title", ""),
        source=data.get("source", ""),
        timeframe=data.get("timeframe", ""),
        timeframes=list(data.get("timeframes", [])),
        subtitle=data.get("subtitle"),
        symbol=data.get("symbol"),
        request=ChartRequest(
            kind=ChartRequestKind(request.get("kind", ChartRequestKind.PRICE_LINE.value)),
            symbols=list(request.get("symbols", [])),
            timeframe=request.get("timeframe", ""),
            from_date=request.get("fromDate"),
            to_date=request.get("toDate"),
        ),
    )
