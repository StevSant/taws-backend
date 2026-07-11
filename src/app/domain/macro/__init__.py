"""Macro domain: the Macro Analyst's structured interpretation of macro events (issue #21).

A `MacroEventInterpretation` grounds an event description (rate decision, CPI print, Fed
statement, ...) in the real current `MacroDataProvider` state (FRED rates/CPI + VIX-derived
volatility regime, issue #15) and tags which asset classes are affected and how
(direction + magnitude). Read-only research output — no trading/execution fields, no
persistence port (interpretations are generated on demand, like `domain/consequence`'s
chains). Own bounded context, kept separate from `domain/market/ports/macro_data_provider.py`
(the raw rates/CPI/VIX port this domain consumes) and `domain/scenario/` (a broader
what-if simulation that happens to also produce per-asset-class impacts).
"""
