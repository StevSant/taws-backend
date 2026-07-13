from typing import Annotated, Literal

from pydantic import BaseModel, Field


class _ChartArgs(BaseModel):
    model_config = {"extra": "forbid"}


class RenderPriceChartArgs(_ChartArgs):
    instrument_symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(default="1y", min_length=1, max_length=16)
    chart_type: Literal["candlestick", "line"] = "candlestick"


class RenderComparisonChartArgs(_ChartArgs):
    instrument_symbols: list[Annotated[str, Field(min_length=1, max_length=32)]] = Field(
        min_length=2, max_length=8
    )
    timeframe: str = Field(default="1y", min_length=1, max_length=16)


class RenderMacroChartArgs(_ChartArgs):
    series_key: Literal["rates", "cpi", "vix"] = "rates"
    timeframe: str = Field(default="1y", min_length=1, max_length=16)


class RenderDrawdownChartArgs(_ChartArgs):
    instrument_symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(default="1y", min_length=1, max_length=16)


class RenderDistributionChartArgs(_ChartArgs):
    instrument_symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(default="1y", min_length=1, max_length=16)


class RenderSentimentGaugeArgs(_ChartArgs):
    pass
