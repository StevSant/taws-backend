_ELLIPSIS = "…"


def truncate_label(text: str, max_chars: int) -> str:
    """Shorten `text` to at most `max_chars`, cutting at a word boundary when possible.

    Used for briefing labels: `Briefing` has no title field, only a full-sentence
    executive `summary`, so the note's label snapshot is the summary's opening.
    """
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped

    head = stripped[:max_chars]
    last_space = head.rfind(" ")
    if last_space > 0:
        head = head[:last_space]
    return f"{head.rstrip()}{_ELLIPSIS}"
