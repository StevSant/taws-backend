from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import get_render_chart_use_case
from app.api.v1.schemas import ChartRenderRequest
from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import RenderChart
from app.application.quant.unknown_instrument_error import UnknownInstrumentError

router = APIRouter(prefix="/charts", tags=["charts"])


@router.post("/render")
async def render_chart(
    payload: ChartRenderRequest,
    render_chart_use_case: Annotated[RenderChart, Depends(get_render_chart_use_case)],
) -> dict[str, Any]:
    """Re-render a chart at a new timeframe (the timeframe-toggle path — no LLM involved).

    Returns the same camelCase `ChartSpec` wire dict the chat stream emits, so the frontend
    reuses one renderer. Public like `GET /quant/stats`: chart data is public market data,
    so the timeframe selector works for anonymous visitors too (no per-user data involved,
    no ownership check needed)."""
    try:
        spec = await render_chart_use_case.execute(
            payload.kind,
            [symbol.upper() for symbol in payload.symbols],
            payload.timeframe,
            payload.from_date,
            payload.to_date,
        )
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return serialize_chart_spec(spec)
