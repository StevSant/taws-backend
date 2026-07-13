class MacroDataUnavailableError(RuntimeError):
    """Raised when a real macro observation (rates, CPI, volatility regime) can't be fetched.

    Same rule as [`MarketDataUnavailableError`][app.domain.market.errors]: real numbers or an
    error, never a stand-in. Macro fixtures are arguably more dangerous than fake prices,
    because a wrong policy rate or CPI print does not *look* wrong — nobody double-takes at
    "CPI 3.1%" the way they would at "BTC $333" — so it survives review and quietly anchors
    the whole macro narrative the agent tells the user.
    """

    def __init__(self, indicator: str, reason: str | None = None) -> None:
        self.indicator = indicator
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"No real macro data available for {indicator}{detail}")
