from collections.abc import AsyncIterator
from datetime import date

from app.application.chat.use_cases.resolve_grounding_context import ResolveGroundingContext
from app.domain.agents.entities import AgentStreamEvent, Message
from app.domain.agents.ports import AgentRunner
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository


class StreamReply:
    """Streams an assistant reply as `AgentStreamEvent`s via the agent layer.

    Depends only on ports — the application layer knows nothing about LangGraph or any
    specific graph shape. Per-thread history is the `AgentRunner`'s (checkpointer's) job,
    keyed by `thread_id`; this use case no longer persists messages itself.

    An optional reference (`asset_symbol` OR `news_id`, at most one) is resolved to a
    `grounding_context` string via the injected `InstrumentUniverse` / `NewsItemRepository`
    ports and forwarded to the runner so the agent answer is grounded on that asset/news
    (issue #73). No reference resolves to `None` and behaves exactly as before.

    `locale` (issue #67) is the language the reply must be written in, already resolved by
    the caller via `ResolveLocale` — this use case just carries it to the agent layer.
    """

    def __init__(
        self,
        agent_runner: AgentRunner,
        instrument_universe: InstrumentUniverse,
        news_item_repository: NewsItemRepository,
    ) -> None:
        self._agent_runner = agent_runner
        self._resolve_grounding_context = ResolveGroundingContext(
            instrument_universe=instrument_universe,
            news_item_repository=news_item_repository,
        )

    async def execute(
        self,
        thread_id: str,
        message: Message,
        user_id: str,
        locale: str,
        asset_symbol: str | None = None,
        news_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        grounding_context = await self._resolve_grounding_context.execute(
            asset_symbol=asset_symbol,
            news_id=news_id,
            from_date=from_date,
            to_date=to_date,
        )
        async for event in self._agent_runner.stream(
            thread_id, message, user_id, locale, grounding_context=grounding_context
        ):
            yield event
