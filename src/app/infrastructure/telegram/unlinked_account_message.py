from typing import Final

UNLINKED_ACCOUNT_MESSAGE: Final[str] = (
    "This Telegram chat isn't linked to a TAWS account yet. Open the TAWS app, go to "
    "your Telegram settings, and tap the generated link to connect this chat before "
    "using /briefing, /signal, or /simular."
)
"""Shared reply for every command that requires a linked account (issue #19) — every
new command except `/start`, which performs the linking itself."""
