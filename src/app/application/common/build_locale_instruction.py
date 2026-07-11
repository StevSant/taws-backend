_LOCALE_INSTRUCTION_TEMPLATE = (
    "\n\nRespond in the locale '{locale}': write every narrative, reasoning, summary, and "
    "recommendation string in that language, regardless of the language used above."
)


def build_locale_instruction(locale: str) -> str:
    """Return a system-prompt suffix instructing the model to respond in `locale`.

    Appended to every LLM-facing system prompt across the signal/briefing/scenario
    pipelines (see each use case's `execute(..., locale: str)` parameter) instead of
    maintaining separate prompt sets per locale — cheaper to write and maintain given the
    personas/prompts already exist per specialist.
    """
    return _LOCALE_INSTRUCTION_TEMPLATE.format(locale=locale)
