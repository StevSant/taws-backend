from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildSentimentGauge


def build_render_sentiment_gauge_tool(
    build_sentiment_gauge: BuildSentimentGauge,
) -> StructuredTool:
    """`render_sentiment_gauge`: current Crypto Fear & Greed index as a gauge.
    Emits the chart over the SSE custom channel; returns the gauge title to the LLM."""

    class _Args(BaseModel):
        pass

    async def _run() -> str:
        spec = await build_sentiment_gauge.execute()
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return spec.meta.title

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_sentiment_gauge",
        description=(
            "Render an inline gauge showing the current Crypto Fear & Greed index, "
            "from real sentiment data. Use when the user asks about market sentiment or "
            "the fear and greed index."
        ),
        args_schema=_Args,
    )
