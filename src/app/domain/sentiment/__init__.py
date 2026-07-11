"""Sentiment domain: the Sentiment Analyst's news-tone + Fear & Greed readings (issue #21).

A `SentimentReading` is a structured, per-instrument tone score (grounded in real,
dated/sourced news) plus the current market-wide Fear & Greed Index reading. Read-only
research output — no trading/execution fields, no persistence port (readings are
generated on demand, like `domain/consequence`'s chains). Own bounded context, kept
separate from `domain/signals/` (an Analyst-produced impact call on an instrument's
outlook) and `domain/macro/` (economy-wide rate/CPI/VIX interpretation).
"""
