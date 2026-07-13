from pydantic import BaseModel, Field


class NewsSentimentScore(BaseModel):
    """One article's tone score, addressed back to its article by position.

    `index` is the article's 0-based position in the numbered list the prompt sent, NOT a
    database id: the model never sees an id (it has no use for one, and feeding it UUIDs
    invites it to hallucinate them back). Positional addressing is what lets one LLM call
    score a whole batch and still land each score on the right row — see
    `ScoreNewsSentiment._score_chunk`, which drops any index outside the chunk rather than
    trusting it.
    """

    index: int = Field(
        ge=0,
        description="0-based position of the article in the numbered list you were given.",
    )
    score: float = Field(
        ge=-1.0,
        le=1.0,
        description=(
            "Tone of THIS article for the market, from -1.0 (very negative) to 1.0 (very "
            "positive). Use a value near 0.0 for routine, procedural, or purely factual "
            "items with no clear directional tone — never guess a direction to seem useful."
        ),
    )
