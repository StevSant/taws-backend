from typing import Any

from app.domain.charts.entities import ChartSeries, ChartSpec


def serialize_chart_spec(spec: ChartSpec) -> dict[str, Any]:
    """Serialize a `ChartSpec` to the camelCase wire dict the frontend consumes verbatim.

    This is the ONE place the wire shape is defined; both the chart tools (which push it
    over the SSE custom channel) and `POST /charts/render` (which returns it) call this,
    so backend and frontend never drift. Kept as a plain function (not `dataclasses.asdict`)
    so the key casing (`xAxis`/`yAxis`) and the points-vs-bars split are explicit."""
    return {
        "type": spec.type.value,
        "series": [_serialize_series(series) for series in spec.series],
        "xAxis": {
            "label": spec.x_axis.label,
            "type": spec.x_axis.type,
            "format": spec.x_axis.format,
        },
        "yAxis": {
            "label": spec.y_axis.label,
            "type": spec.y_axis.type,
            "format": spec.y_axis.format,
        },
        "meta": {
            "title": spec.meta.title,
            "subtitle": spec.meta.subtitle,
            "source": spec.meta.source,
            "symbol": spec.meta.symbol,
            "timeframe": spec.meta.timeframe,
            "timeframes": list(spec.meta.timeframes),
            "request": {
                "kind": spec.meta.request.kind.value,
                "symbols": list(spec.meta.request.symbols),
                "timeframe": spec.meta.request.timeframe,
                "fromDate": spec.meta.request.from_date,
                "toDate": spec.meta.request.to_date,
            },
        },
    }


def _serialize_series(series: ChartSeries) -> dict[str, Any]:
    return {
        "name": series.name,
        "points": [{"x": point.x, "y": point.y} for point in series.points],
        "bars": [
            {"t": bar.t, "o": bar.o, "h": bar.h, "l": bar.l, "c": bar.c, "v": bar.v}
            for bar in series.bars
        ],
    }
