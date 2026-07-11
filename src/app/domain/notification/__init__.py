"""Notification domain: Watchdog/Notifier-agent alerts and the delivery-channel port.

An `Alert` is a composed, ready-to-send notification derived from a `Signal` (issue #10).
`NotificationChannel` is the delivery port — this issue ships one no-op/logging adapter;
the Telegram delivery adapter (issue #14) implements the same port, unchanged.
"""
