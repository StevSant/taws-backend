def format_unknown_command_reply() -> str:
    return (
        "⚠️ <b>Unknown Command</b>"
        "\n\nI didn't recognize that command."
        "\n\n━━━━━━━━━━━━━━━━━━"
        "\n\n<b>Available Commands</b>"
        "\n\n• /briefing — your latest watchlist briefing"
        "\n• /signal TICKER — latest signal for an instrument"
        "\n• /simular text — run a what-if scenario simulation"
        "\n• /impact sector — how the latest news affects a sector"
        "\n\n━━━━━━━━━━━━━━━━━━"
        "\n\nOr just send me a message."
    )
