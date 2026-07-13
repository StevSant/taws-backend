from fastapi import Request, status
from fastapi.responses import JSONResponse


async def market_data_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map `MarketDataUnavailableError` to `503 Service Unavailable`.

    503 rather than 500: the upstream price provider is temporarily unreachable (a
    CoinGecko 429, most often), the request itself was fine, and retrying later is the
    right move — which is exactly what 503 tells a client.

    Registered app-wide so every price-backed endpoint (quant stats, event study, chart
    render) reports the outage the same way, and so an endpoint added later inherits the
    behaviour instead of having to remember it. What must never happen — and used to — is
    a 200 carrying an invented price.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
    )
