def format_welcome_reply() -> str:
    """Render the welcome message sent when a user sends `/start` without a linking
    token — a friendly introduction to what the bot can do.
    """
    return (
        "Welcome to TAWS! I'm your trading assistant.\n\n"
        "You can talk to me naturally about markets, or use these commands:\n"
        "/briefing — your latest watchlist briefing\n"
        "/signal <TICKER> — the latest signal for an instrument (e.g. /signal AAPL)\n"
        "/simular <text> — run a what-if scenario simulation\n"
        "/impact <sector> — how the latest news affects a sector (e.g. /impact Technology)\n\n"
        "Just send me a message and I'll help you out!"
    )