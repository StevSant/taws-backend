"""Market domain: instruments, news, and prices — entities and ports.

Powers the Track-5 "Market Radar" data layer: news linked to instruments across
asset classes, plus OHLC price series for quant/signal work downstream. No
framework or vendor imports allowed here — see `infrastructure/` for adapters.
"""
