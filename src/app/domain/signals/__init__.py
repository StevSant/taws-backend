"""Signals domain: the Analyst agent's news-to-instrument impact calls — entities and ports.

A `Signal` is an alert/task-shaped record only — impact classification, confidence,
evidence, and an optional price delta for context. No trading/execution fields (no
buy/sell/order/quantity/price_target) exist here or anywhere downstream.
"""
