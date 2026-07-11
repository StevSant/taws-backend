import logging
from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.application.watchdog import AlertedSignalTracker
from app.core.config import Settings, get_settings
from app.domain.agents.ports import (
    AgentMemory,
    AgentRunner,
    EmbeddingProvider,
    LLMProvider,
    VectorStore,
)
from app.domain.briefing.ports import BriefingRepository
from app.domain.chat.ports import ConversationRepository
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider, NewsProvider
from app.domain.notification.ports import NotificationChannel
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.agents import LangGraphAgentRunner, build_supervisor_graph
from app.infrastructure.agents.tools import build_advisor_grounding_tools
from app.infrastructure.embeddings import OpenAIEmbeddings
from app.infrastructure.llm import OpenAIProvider, build_chat_model
from app.infrastructure.marketdata import (
    CoinGeckoMarketDataProvider,
    FixtureMarketDataProvider,
    RoutingMarketDataProvider,
    YFinanceMarketDataProvider,
)
from app.infrastructure.memory import InMemoryCheckpointer, RedisCheckpointer
from app.infrastructure.news import (
    AggregatingNewsProvider,
    FinnhubNewsProvider,
    FixtureNewsProvider,
    MarketauxNewsProvider,
    NewsApiNewsProvider,
    RssNewsProvider,
)
from app.infrastructure.notification import LoggingNotificationChannel
from app.infrastructure.persistence import (
    SupabaseBriefingRepository,
    SupabaseConversationRepository,
    SupabaseSignalRepository,
    SupabaseWatchlistRepository,
)
from app.infrastructure.seeds import load_universe_seed
from app.infrastructure.universe import JsonInstrumentUniverse
from app.infrastructure.vectorstore import PgvectorStore


class Container:
    """Wires domain ports to infrastructure adapters, based on `Settings`.

    This is the single place that decides which adapter implements which port. To
    swap a provider (e.g. add Anthropic): create the adapter in `infrastructure/`,
    then change the relevant `get_*` method below — nothing else in the codebase
    needs to know.

    Every adapter is built lazily and cached on first access, so each is a
    process-wide singleton for the lifetime of this `Container` (itself cached by
    `get_container`) — e.g. the `AsyncOpenAI` client, the LangChain chat model, the
    compiled graph, and the `AgentRunner` are each constructed once.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm_provider: LLMProvider | None = None
        self._embedding_provider: EmbeddingProvider | None = None
        self._vector_store: VectorStore | None = None
        self._agent_memory: AgentMemory | None = None
        self._conversation_repository: ConversationRepository | None = None
        self._watchlist_repository: WatchlistRepository | None = None
        self._signal_repository: SignalRepository | None = None
        self._briefing_repository: BriefingRepository | None = None
        self._news_provider: NewsProvider | None = None
        self._instrument_universe: InstrumentUniverse | None = None
        self._market_data_provider: MarketDataProvider | None = None
        self._chat_model: BaseChatModel | None = None
        self._chat_graph: Any | None = None
        self._agent_runner: AgentRunner | None = None
        self._notification_channel: NotificationChannel | None = None
        self._alerted_signal_tracker: AlertedSignalTracker | None = None

    def get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = OpenAIProvider(
                api_key=self._settings.openai_api_key, model=self._settings.openai_model
            )
        return self._llm_provider

    def get_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = OpenAIEmbeddings(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_embedding_model,
            )
        return self._embedding_provider

    def get_vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = PgvectorStore(database_url=self._settings.database_url)
        return self._vector_store

    def get_agent_memory(self) -> AgentMemory:
        if self._agent_memory is None:
            # Key fallback logic: Redis (Upstash) when configured AND reachable,
            # in-memory otherwise — a missing URL, a bad URL, or a server without the
            # required modules must never break chat, only lose durable memory.
            if self._settings.redis_url:
                redis_memory = RedisCheckpointer(redis_url=self._settings.redis_url)
                try:
                    redis_memory.get_checkpointer()  # probe: connects + creates indices
                    self._agent_memory = redis_memory
                except Exception:  # noqa: BLE001 — any Redis failure degrades, never breaks
                    logging.getLogger(__name__).warning(
                        "REDIS_URL is set but the Redis checkpointer failed to "
                        "initialize; falling back to InMemoryCheckpointer",
                        exc_info=True,
                    )
                    self._agent_memory = InMemoryCheckpointer()
            else:
                self._agent_memory = InMemoryCheckpointer()
        return self._agent_memory

    def get_conversation_repository(self) -> ConversationRepository:
        if self._conversation_repository is None:
            self._conversation_repository = SupabaseConversationRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
            )
        return self._conversation_repository

    def get_watchlist_repository(self) -> WatchlistRepository:
        if self._watchlist_repository is None:
            self._watchlist_repository = SupabaseWatchlistRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
            )
        return self._watchlist_repository

    def get_signal_repository(self) -> SignalRepository:
        if self._signal_repository is None:
            self._signal_repository = SupabaseSignalRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
            )
        return self._signal_repository

    def get_briefing_repository(self) -> BriefingRepository:
        if self._briefing_repository is None:
            self._briefing_repository = SupabaseBriefingRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
            )
        return self._briefing_repository

    def get_notification_channel(self) -> NotificationChannel:
        """Return the cached Watchdog alert delivery channel.

        `LoggingNotificationChannel` today (no-op/logging stand-in) — swap in
        `TelegramNotificationChannel` here once issue #14 lands; nothing in
        `application/` or `api/` needs to change, since both depend on the
        `NotificationChannel` port, not this adapter.
        """
        if self._notification_channel is None:
            self._notification_channel = LoggingNotificationChannel()
        return self._notification_channel

    def get_alerted_signal_tracker(self) -> AlertedSignalTracker:
        """Return the cached, process-wide `AlertedSignalTracker` singleton.

        Shared between the scheduler's periodic Watchdog scan job and the manual
        "Scan now" endpoint so both draw from the same in-process novelty/dedup state —
        see `AlertedSignalTracker`'s docstring for why this isn't persisted.
        """
        if self._alerted_signal_tracker is None:
            self._alerted_signal_tracker = AlertedSignalTracker()
        return self._alerted_signal_tracker

    def get_news_provider(self) -> NewsProvider:
        """Return the aggregated news source for the radar/agents.

        Fans out to every configured live source (Marketaux, NewsAPI, Finnhub,
        RSS) concurrently; a source with no API key configured is left out of
        the fan-out entirely. Falls back to `FixtureNewsProvider` whenever no
        live source is configured, or all of them fail / return nothing — see
        `AggregatingNewsProvider` for the merge/dedupe/link/filter pipeline.
        """
        if self._news_provider is None:
            live_providers: list[NewsProvider] = []
            if self._settings.marketaux_api_key:
                live_providers.append(
                    MarketauxNewsProvider(
                        api_key=self._settings.marketaux_api_key,
                        base_url=self._settings.marketaux_base_url,
                        languages=self._settings.marketaux_languages,
                        timeout_seconds=self._settings.marketaux_timeout_seconds,
                        max_pages=self._settings.marketaux_max_pages,
                    )
                )
            if self._settings.newsapi_api_key:
                live_providers.append(
                    NewsApiNewsProvider(
                        api_key=self._settings.newsapi_api_key,
                        base_url=self._settings.newsapi_base_url,
                        default_query=self._settings.newsapi_default_query,
                    )
                )
            if self._settings.finnhub_api_key:
                live_providers.append(
                    FinnhubNewsProvider(
                        api_key=self._settings.finnhub_api_key,
                        base_url=self._settings.finnhub_base_url,
                    )
                )
            if self._settings.rss_feed_urls:
                live_providers.append(RssNewsProvider(feed_urls=self._settings.rss_feed_urls))

            fixture_provider = FixtureNewsProvider(seed_path=self._settings.news_fixture_seed_path)
            self._news_provider = AggregatingNewsProvider(
                providers=live_providers,
                fixture_provider=fixture_provider,
                instrument_universe=self.get_instrument_universe(),
            )
        return self._news_provider

    def get_instrument_universe(self) -> InstrumentUniverse:
        if self._instrument_universe is None:
            self._instrument_universe = JsonInstrumentUniverse(
                seed_path=self._settings.universe_seed_path
            )
        return self._instrument_universe

    def get_market_data_provider(self) -> MarketDataProvider:
        """Return the routing MarketDataProvider (CoinGecko/yfinance + fixture fallback).

        `yfinance`/CoinGecko symbol overrides come straight from the universe
        seed's optional `yfinance_symbol` / `coingecko_id` rows — those vendor
        details never touch the pure `Instrument` entity.
        """
        if self._market_data_provider is None:
            universe_rows = load_universe_seed(self._settings.universe_seed_path)
            yfinance_overrides = {
                row["symbol"]: row["yfinance_symbol"]
                for row in universe_rows
                if row.get("yfinance_symbol")
            }
            coingecko_overrides = {
                row["symbol"]: row["coingecko_id"]
                for row in universe_rows
                if row.get("coingecko_id")
            }
            fixture_provider = FixtureMarketDataProvider()
            self._market_data_provider = RoutingMarketDataProvider(
                yfinance_provider=YFinanceMarketDataProvider(symbol_overrides=yfinance_overrides),
                coingecko_provider=CoinGeckoMarketDataProvider(
                    base_url=self._settings.coingecko_base_url,
                    coingecko_id_overrides=coingecko_overrides,
                ),
                fixture_provider=fixture_provider,
            )
        return self._market_data_provider

    def get_agent_runner(self) -> AgentRunner:
        """Return the cached `AgentRunner`, built from the chat model + checkpointer.

        See `infrastructure/llm/chat_model_factory.build_chat_model` to swap the LLM
        provider behind agent graphs, and `infrastructure/agents/supervisor_graph.
        build_supervisor_graph` to change the graph shape — this method only wires
        them together.
        """
        if self._agent_runner is None:
            self._agent_runner = LangGraphAgentRunner(graph=self._get_chat_graph())
        return self._agent_runner

    def _get_chat_model(self) -> BaseChatModel:
        """Build/cache the LangChain chat model used ONLY by the chat/SSE agent graph
        below. The Analyst signal / Advisor briefing pipelines do NOT use this — they
        depend on the `LLMProvider` port (`get_llm_provider()`) instead, per the
        hexagonal rule that `application/` never imports a vendor/framework package
        directly (see `application/signals/use_cases/generate_signal.py`'s docstring).
        Kept private for that reason: nothing outside `_get_chat_graph` should reach for
        a raw `BaseChatModel`.
        """
        if self._chat_model is None:
            self._chat_model = build_chat_model(self._settings)
        return self._chat_model

    def _get_chat_graph(self) -> Any:
        if self._chat_graph is None:
            checkpointer = self.get_agent_memory().get_checkpointer()
            # Signal-only: see `build_advisor_grounding_tools`'s docstring for why
            # briefing/watchlist grounding tools were removed (unauthenticated chat
            # route + no per-user ownership check would leak cross-tenant data).
            advisor_tools = build_advisor_grounding_tools(
                signal_repository=self.get_signal_repository()
            )
            self._chat_graph = build_supervisor_graph(
                self._get_chat_model(), checkpointer, advisor_tools=advisor_tools
            )
        return self._chat_graph


@lru_cache
def get_container() -> Container:
    """Return a process-wide cached Container, built from the cached Settings."""
    return Container(settings=get_settings())
