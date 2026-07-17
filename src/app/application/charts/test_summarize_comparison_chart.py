from app.application.charts.summarize_comparison_chart import summarize_comparison_chart
from app.domain.charts.entities import (
    ChartAxis,
    ChartMeta,
    ChartPoint,
    ChartRequest,
    ChartRequestKind,
    ChartSeries,
    ChartSpec,
    ChartType,
)


def test_summary_explains_rebased_values_as_returns_over_actual_window() -> None:
    spec = ChartSpec(
        type=ChartType.COMPARISON,
        series=[
            ChartSeries(
                name="BTC",
                points=[
                    ChartPoint(x="2026-01-15T00:00:00+00:00", y=100.0),
                    ChartPoint(x="2026-07-15T00:00:00+00:00", y=67.0),
                ],
            ),
            ChartSeries(
                name="BNB",
                points=[
                    ChartPoint(x="2026-01-15T00:00:00+00:00", y=100.0),
                    ChartPoint(x="2026-07-15T00:00:00+00:00", y=59.0),
                ],
            ),
        ],
        x_axis=ChartAxis(label="Date", type="time"),
        y_axis=ChartAxis(label="Rebased to 100", type="value", format="number"),
        meta=ChartMeta(
            title="BTC vs BNB - 6M (rebased)",
            source="market data",
            timeframe="6m",
            request=ChartRequest(
                kind=ChartRequestKind.COMPARISON,
                symbols=["BTC", "BNB"],
                timeframe="6m",
            ),
        ),
    )

    summary = summarize_comparison_chart(spec)

    assert "normalized performance index, not asset prices" in summary
    assert "2026-01-15 to 2026-07-15" in summary
    assert "BTC: 100.00 -> 67.00 (-33.00%)" in summary
    assert "BNB: 100.00 -> 59.00 (-41.00%)" in summary
