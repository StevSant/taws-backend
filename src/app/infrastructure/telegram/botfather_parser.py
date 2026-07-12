import re

_BOT_TOKEN_PATTERN = re.compile(r"\b(\d{8,10}:[A-Za-z0-9_-]{35,})\b")
_BOT_USERNAME_PATTERN = re.compile(r"t\.me/([A-Za-z]\w+)")


class BotfatherParseResult:
    """Result of parsing BotFather's welcome message."""

    def __init__(self, bot_token: str, bot_username: str) -> None:
        self.bot_token = bot_token
        self.bot_username = bot_username


def parse_botfather_text(text: str) -> BotfatherParseResult | None:
    """Extract `bot_token` and `bot_username` from BotFather's welcome message.

    BotFather's message looks like:
        Done! Congratulations on your new bot. You will find it at
        t.me/MidasTestBot. ...
        Use this token to access the HTTP API:
        8683925755:AAEkpC1KdpjlYd07hzsDswXUHZjYSaF1Q2k

    Returns `None` if either the token or username can't be extracted.
    """
    token_match = _BOT_TOKEN_PATTERN.search(text)
    username_match = _BOT_USERNAME_PATTERN.search(text)

    if not token_match or not username_match:
        return None

    return BotfatherParseResult(
        bot_token=token_match.group(1),
        bot_username=username_match.group(1),
    )
