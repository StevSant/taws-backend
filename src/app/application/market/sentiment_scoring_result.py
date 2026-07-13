from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SentimentScoringResult:
    """What one `ScoreNewsSentiment` pass did — for the scheduler log and the manual endpoint.

    `considered` is how many unscored articles the pass pulled (capped by `batch_size`), and
    `scored + failed` need not equal it: the model is allowed to omit an article it could not
    place, and an omitted one is neither scored nor failed — it just stays NULL and comes back
    on the next tick. `considered == batch_size` is the signal that a backlog remains.
    """

    considered: int
    scored: int
    failed: int
