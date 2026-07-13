_LOCALE_INSTRUCTION_TEMPLATE = (
    "\n\nOUTPUT LANGUAGE — this rule overrides everything else in this prompt.\n"
    "Write EVERY word you output in the locale '{locale}': every narrative, thesis, reasoning, "
    "summary, driver, risk, label and recommendation string.\n"
    "The source material you are given — news articles, headlines, tool results, retrieved "
    "documents, market data, prior analyses — is very often written in ENGLISH. That is "
    "irrelevant. Do NOT mirror the language of your input. Read it in whatever language it "
    "arrives in, then WRITE your answer in '{locale}', translating any phrase you take from it.\n"
    "This holds no matter where that material appears — before this instruction or after it, in "
    "a system message, a user message, or a tool result. Never switch language mid-answer. If "
    "your reply is not entirely in '{locale}', it is wrong."
)


def build_locale_instruction(locale: str) -> str:
    """Return a system-prompt suffix instructing the model to respond in `locale`.

    Appended to every LLM-facing system prompt across the chat/signal/briefing/scenario/
    sentiment pipelines (see each use case's `execute(..., locale: str)` parameter) instead of
    maintaining separate prompt sets per locale — cheaper to write and maintain given the
    personas/prompts already exist per specialist.

    **Why the wording is this emphatic.** The previous version read "…regardless of the language
    used above", and every pipeline here puts its source material *below* the system prompt: the
    signal classifier appends the (English) news article as the USER message, and the chat
    specialists append (English) `ToolMessage` blobs after this instruction — see
    `infrastructure/agents/invoke_with_bound_tools.py`. So the instruction, by its own wording,
    did not cover the one thing most likely to flip the model's language, and it sat far from the
    recency slot while a wall of English sat in it. In practice the model mirrored its input:
    Spanish-locale users got English signal theses (English news in, English thesis out) and chat
    replies that switched to English the moment a tool fired. Naming the failure mode explicitly
    — "your input is English, that is irrelevant, translate it" — is what actually holds, because
    mirroring the input language is the model's default behavior and has to be countermanded, not
    merely omitted.

    Position matters as well as wording: for the tool-calling chat path this string is *also*
    re-asserted after the tool results, so it lands in the recency slot rather than being buried
    above them.
    """
    return _LOCALE_INSTRUCTION_TEMPLATE.format(locale=locale)
