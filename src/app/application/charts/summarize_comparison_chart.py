from app.domain.charts.entities import ChartSpec


def summarize_comparison_chart(spec: ChartSpec) -> str:
    """Describe a rebased comparison without mistaking index values for asset prices."""
    populated = [series for series in spec.series if series.points]
    if not populated:
        return "Rendered a normalized performance comparison with no plottable series."

    first_date = min(series.points[0].x for series in populated).split("T", maxsplit=1)[0]
    last_date = max(series.points[-1].x for series in populated).split("T", maxsplit=1)[0]
    results: list[str] = []
    for series in populated:
        start = series.points[0].y
        end = series.points[-1].y
        return_pct = ((end / start) - 1) * 100 if start else 0.0
        results.append(f"{series.name}: {start:.2f} -> {end:.2f} ({return_pct:+.2f}%)")

    return (
        f"Rendered a {spec.meta.timeframe} normalized performance comparison from "
        f"{first_date} to {last_date}. Values are a normalized performance index, not asset "
        f"prices: {'; '.join(results)}."
    )
