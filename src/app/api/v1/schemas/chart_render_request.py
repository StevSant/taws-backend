from pydantic import BaseModel, Field

from app.domain.charts.entities import ChartRequestKind

_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class ChartRenderRequest(BaseModel):
    """Request body for `POST /api/v1/charts/render` — re-render a chart at a new timeframe.

    `from_date`/`to_date` (ISO `YYYY-MM-DD`) are an optional custom range. When both are set
    and valid they take precedence over `timeframe`; an invalid/partial range falls back to
    the timeframe preset in the use case (never a hard error).

    The custom range currently applies to the price chart kinds only (`price_candlestick`,
    `price_line`). Other kinds (comparison, drawdown, distribution, macro, sentiment) render
    over the `timeframe` preset and ignore `from_date`/`to_date` — do not rely on the range
    narrowing those."""

    kind: ChartRequestKind
    symbols: list[str] = Field(default_factory=list, max_length=8)
    timeframe: str = Field(default="", max_length=10)
    from_date: str | None = Field(
        default=None,
        pattern=_ISO_DATE_PATTERN,
        description="Inclusive range start (ISO YYYY-MM-DD); price chart kinds only, else ignored.",
    )
    to_date: str | None = Field(
        default=None,
        pattern=_ISO_DATE_PATTERN,
        description="Inclusive range end (ISO YYYY-MM-DD); price chart kinds only, else ignored.",
    )
