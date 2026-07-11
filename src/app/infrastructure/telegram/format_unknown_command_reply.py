def format_unknown_command_reply() -> str:
    """Render the helpful reply sent for `UnknownCommand` (issue #19) — an unrecognized
    or malformed command, rather than the silent no-op an ordinary chat message gets.
    Lists every supported command so the user can self-correct without leaving Telegram.
    """
    return (
        "Sorry, I didn't understand that command.\n\n"
        "Available commands:\n"
        "/briefing — your latest watchlist briefing\n"
        "/signal <TICKER> — the latest signal for an instrument (e.g. /signal AAPL)\n"
        "/simular <text> — run a what-if scenario simulation\n"
        "/impact <sector> — how the latest news event affects a sector (e.g. /impact Technology)"
    )
