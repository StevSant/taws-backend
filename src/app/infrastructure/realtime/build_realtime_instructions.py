from app.application.common import build_locale_instruction
from app.infrastructure.realtime.realtime_instructions import REALTIME_INSTRUCTIONS

_SPOKEN_LANGUAGE_TEMPLATE = (
    "\n\nSPEAK IN '{locale}'. Every word you say aloud is in that language, from your very first "
    "syllable — including greetings, filler, and the way you read out numbers and tickers. Your "
    "tools return English text (news headlines, signal theses, market data); you must still SPEAK "
    "'{locale}', translating what you take from them. Never switch language mid-sentence or "
    "mid-conversation, and never answer in English just because a tool result was in English. Keep "
    "instrument tickers themselves (AAPL, BTC) as-is — those are names, not words to translate."
)


def build_realtime_instructions(locale: str) -> str:
    """Return the TAWS Voice system instructions, pinned to `locale`.

    `REALTIME_INSTRUCTIONS` is authored entirely in English and — unlike every other LLM-facing
    prompt in this codebase — never carried a language rule at all: neither realtime transport
    passed a locale, so `build_locale_instruction` was never appended. An English persona plus
    English tool output is exactly the input a Realtime model mirrors, which is why the voice
    agent drifted into English mid-conversation for Spanish users even though the WebRTC mint
    hardcoded `"language": "es"` — that field only hints the *input* transcriber, and says
    nothing about the language the model speaks back.

    Reuses the shared `build_locale_instruction` so the voice agent can't drift to a different
    phrasing of the same rule than text chat, and adds a spoken-form clause on top of it (voice
    has failure modes text doesn't: greeting in the wrong language before any tool has run, and
    reading numbers/tickers aloud).
    """
    return (
        REALTIME_INSTRUCTIONS
        + build_locale_instruction(locale)
        + _SPOKEN_LANGUAGE_TEMPLATE.format(locale=locale)
    )
