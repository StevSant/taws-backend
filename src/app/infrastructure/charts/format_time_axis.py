from matplotlib.axes import Axes

_MAX_TICKS = 6


def format_time_axis(axes: Axes, x_labels: list[str]) -> None:
    """Label a numeric x-axis with up to ~6 date ticks drawn from ISO timestamp strings.

    Time-series builders plot y against a plain integer index (not matplotlib dates) to keep
    even sampling simple, then call this to place a handful of readable `YYYY-MM-DD` ticks.
    Shared by the line/area/candlestick/comparison/drawdown builders so the tick logic lives
    in one place."""
    count = len(x_labels)
    if count == 0:
        return
    step = max(1, count // _MAX_TICKS)
    positions = list(range(0, count, step))
    axes.set_xticks(positions)
    axes.set_xticklabels([x_labels[index][:10] for index in positions], rotation=0)
