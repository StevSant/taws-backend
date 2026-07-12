def format_unknown_command_reply() -> str:
    return (
        "⚠️ <b>Comando no reconocido</b>"
        "\n\nNo reconocí ese comando."
        "\n\n━━━━━━━━━━━━━━━━━━"
        "\n\n<b>Comandos Disponibles</b>"
        "\n\n• /briefing — tu último briefing de la watchlist"
        "\n• /signal TICKER — última señal para un instrumento"
        "\n• /simular texto — simula un escenario what-if"
        "\n• /impact sector — cómo afecta la última noticia a un sector"
        "\n\n━━━━━━━━━━━━━━━━━━"
        "\n\nO envíame un mensaje directo."
    )
