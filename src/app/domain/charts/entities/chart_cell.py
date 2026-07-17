from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartCell:
    """A single labelled cell of a `heatmap` `ChartSpec`.

    `value` is the metric that drives the tile's color (e.g. a percentage change, colored
    by sign). Used only by `ChartType.HEATMAP`, where `ChartSpec.cells` replaces the
    `series`/`bars` split that time-series charts use — a heatmap has no axes, just a grid
    of labelled values."""

    label: str
    value: float
