from app.domain.market.errors import MarketDataUnavailableError


def market_data_unavailable_message(symbol: str, error: MarketDataUnavailableError) -> str:
    """The one thing every market-data tool says to the model when it has no real prices.

    A tool result is the model's ground truth: it has no way to tell a real figure from an
    invented one, so whatever this returns is what the user is told. That makes the wording
    load-bearing, and it has to do two jobs at once — report the outage, and explicitly
    close the door on the model filling the gap from memory or "reasonable" estimation.
    Both failure modes end the same way: a confident, fabricated number presented to
    someone deciding whether to invest.

    Kept in one place so a tool added later cannot quietly invent a softer phrasing that
    leaves that door open.
    """
    return (
        f"Market data for {symbol} is UNAVAILABLE — the upstream price provider could not be "
        f"reached ({error.reason or 'provider error'}). You have NO price data for {symbol}. "
        f"Tell the user the data is unavailable and that you cannot analyze or chart it right "
        f"now, and suggest they retry shortly. Do NOT state or estimate a price, a price "
        f"change, a trend, or a volatility figure, and do not answer from memory or from other "
        f"tools' output — any such number would be fabricated."
    )
