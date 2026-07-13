class NewsUnavailableError(RuntimeError):
    """Raised when every configured news provider failed — an outage, not "no news today".

    The distinction matters and must not be collapsed. An empty result is a real answer
    ("nothing matched your filters"); a total provider failure is the absence of an answer.
    Returning `[]` for the second case tells the agent there is no news, which it will
    happily narrate as a finding — "no hay noticias recientes sobre BTC" — which is itself a
    false claim about the world.

    What this replaced was worse still: the aggregator used to fall back to canned fixture
    articles, so an outage produced *invented headlines with invented `example.com` URLs*,
    presented to the user as sourced reporting and cited by the analyst as evidence.
    """

    def __init__(self, provider_count: int, reason: str | None = None) -> None:
        self.provider_count = provider_count
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"All {provider_count} news provider(s) failed{detail}")
