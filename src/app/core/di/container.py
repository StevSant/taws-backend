import logging
from datetime import timedelta
from functools import lru_cache
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.analysis.use_cases import RefreshTrackedAnalysis
from app.application.charts.use_cases import (
    BuildComparisonChart,
    BuildDistributionChart,
    BuildDrawdownChart,
    BuildMacroChart,
    BuildPriceChart,
    BuildSentimentGauge,
    RenderChart,
)
from app.application.chat.use_cases import GenerateConversationTitle
from app.application.consequence.use_cases import GenerateConsequenceChain
from app.application.event_intelligence import ProcessedEventTracker
from app.application.event_intelligence.use_cases import (
    AnalyzeEventImpact,
    BroadcastImportantEvents,
    ProcessIncomingEvent,
)
from app.application.instruments.use_cases import (
    ListEnrichedInstruments,
    RegisterInstrument,
    SearchCoins,
)
from app.application.macro.use_cases import InterpretMacroEvent
from app.application.market import NewsFeedRefresher
from app.application.market.use_cases import IngestNews, ScoreNewsSentiment
from app.application.profile.use_cases import ResolveLocale
from app.application.quant.use_cases import ComputeEventStudy, ComputeMarketStats
from app.application.scenario.use_cases import (
    ComputeScenarioQuantification,
    GatherScenarioContext,
    GenerateScenarioAgentContributions,
    NormalizeScenarioIntake,
    SynthesizeScenarioResult,
)
from app.application.sentiment.use_cases import AnalyzeSentiment
from app.application.signals import NewsPrefilterPolicy
from app.application.signals.use_cases import (
    AnalyzePendingNews,
    ForceAnalyzeNewsItem,
    GenerateSignal,
)
from app.application.telegram.use_cases import LinkTelegramAccount
from app.application.watchdog import AlertedSignalTracker
from app.application.watchlist.use_cases import ReorderWatchlists
from app.core.config import Settings, get_settings
from app.domain.agents.ports import (
    AgentMemory,
    AgentRunner,
    EmbeddingProvider,
    LLMProvider,
    RealtimeSessionProvider,
    STTProvider,
    TTSProvider,
    VectorStore,
)
from app.domain.briefing.ports import BriefingDocumentRenderer, BriefingRepository
from app.domain.charts.entities import ChartConfig
from app.domain.chat.ports import ConversationRepository
from app.domain.event_intelligence.ports import (
    EventAnalyzerPort,
    EventRepositoryPort,
    NewsProviderPort,
)
from app.domain.freshness import FreshnessPolicy
from app.domain.market.entities import AssetClass, MacroIndicator
from app.domain.market.ports import (
    CoinGeckoSearchProvider,
    FundamentalsProvider,
    InstrumentCatalogRepository,
    InstrumentMetadataProvider,
    InstrumentUniverse,
    MacroDataProvider,
    MarketDataProvider,
    NewsItemRepository,
    NewsProvider,
)
from app.domain.notes.ports import NoteRepository
from app.domain.notification.ports import EmailSender, NotificationChannel
from app.domain.profile.ports import UserProfileRepository
from app.domain.scenario.entities import ScenarioAgentId
from app.domain.scenario.ports import ScenarioRepository
from app.domain.sentiment.ports import FearGreedProvider, SentimentRepository
from app.domain.signals.ports import SignalRepository
from app.domain.telegram.ports import (
    TelegramLinkRepository,
    TelegramLinkTokenRepository,
    TelegramMessenger,
)
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.agents import LangGraphAgentRunner, build_supervisor_graph
from app.infrastructure.agents.personas import (
    ADVISOR_PERSONA,
    ANALYST_PERSONA,
    CONSEQUENCE_PERSONA,
    MACRO_PERSONA,
    MIDAS_PERSONA,
    MIDAS_VOICE_HINT,
    QUANT_PERSONA,
    SENTIMENT_PERSONA,
)
from app.infrastructure.agents.scenario import ScenarioSimulationRunner, build_scenario_graph
from app.infrastructure.agents.tools import (
    build_advisor_grounding_tools,
    build_analyst_grounding_tools,
    build_consequence_tools,
    build_event_intelligence_tools,
    build_get_fundamentals_tool,
    build_get_macro_state_tool,
    build_get_watchlist_tool,
    build_macro_tools,
    build_market_overview_tools,
    build_quant_grounding_tools,
    build_render_comparison_chart_tool,
    build_render_distribution_chart_tool,
    build_render_drawdown_chart_tool,
    build_render_macro_chart_tool,
    build_render_price_chart_tool,
    build_render_sentiment_gauge_tool,
    build_scenario_tools,
    build_sentiment_tools,
)
from app.infrastructure.briefing import ReportLabBriefingPdfRenderer
from app.infrastructure.embeddings import OpenAIEmbeddings
from app.infrastructure.event_intelligence.gemini import GeminiEventAnalyzer
from app.infrastructure.event_intelligence.providers import MarketNewsEventProvider
from app.infrastructure.event_intelligence.repositories import (
    MemoryEventRepository,
    SupabaseEventRepository,
)
from app.infrastructure.fundamentals import (
    RoutingFundamentalsProvider,
    YFinanceFundamentalsProvider,
)
from app.infrastructure.llm import OpenAIProvider, build_chat_model
from app.infrastructure.macro import (
    FredMacroDataProvider,
    RoutingMacroDataProvider,
)
from app.infrastructure.marketdata import (
    CoinGeckoCoinSearchProvider,
    CoinGeckoInstrumentMetadataProvider,
    CoinGeckoKeyRing,
    CoinGeckoMarketDataProvider,
    RoutingMarketDataProvider,
    YFinanceMarketDataProvider,
)
from app.infrastructure.memory import (
    InMemoryCheckpointer,
    PostgresCheckpointer,
    RedisCheckpointer,
)
from app.infrastructure.news import (
    AggregatingNewsProvider,
    FinnhubNewsProvider,
    MarketauxNewsProvider,
    NewsApiNewsProvider,
    RssNewsProvider,
    SecEdgarNewsProvider,
)
from app.infrastructure.notification import (
    LoggingEmailSender,
    LoggingNotificationChannel,
    TelegramNotificationChannel,
)
from app.infrastructure.persistence import (
    InMemoryNoteRepository,
    SupabaseBriefingRepository,
    SupabaseConversationRepository,
    SupabaseInstrumentCatalogRepository,
    SupabaseNewsItemRepository,
    SupabaseNoteRepository,
    SupabaseScenarioRepository,
    SupabaseSentimentRepository,
    SupabaseSignalRepository,
    SupabaseTelegramLinkRepository,
    SupabaseTelegramLinkTokenRepository,
    SupabaseUserProfileRepository,
    SupabaseWatchlistRepository,
)
from app.infrastructure.realtime import OpenAIRealtimeSessionProvider
from app.infrastructure.seeds import load_preset_scenarios_seed
from app.infrastructure.sentiment import (
    AlternativeMeFearGreedProvider,
    RoutingFearGreedProvider,
)
from app.infrastructure.stt import OpenAISTTProvider
from app.infrastructure.telegram import (
    BriefingCommandHandler,
    ChatMessageHandler,
    EventCallbackHandler,
    ImpactCommandHandler,
    SignalCommandHandler,
    SimulateCommandHandler,
    TelegramBotClient,
)
from app.infrastructure.tts import OpenAITTSProvider
from app.infrastructure.universe import SupabaseInstrumentUniverse
from app.infrastructure.vectorstore import PgvectorStore

# Raised instead of silently degrading to a process-local stand-in outside development.
# Both of these used to be ungated fallbacks, which turned a forgotten secret into invisible
# data loss rather than a failed deploy. Same stance as `PgvectorStore`'s missing-DATABASE_URL
# guard: an unconfigured production dependency is a bug to surface, not a mode to run in.
_NO_REDIS_URL_ERROR = (
    "REDIS_URL is not set and APP_ENV is not 'development'. The agent checkpointer would "
    "fall back to in-process memory, so conversation state would die on restart and differ "
    "per worker. Set REDIS_URL (Upstash) for this environment, or set APP_ENV=development "
    "to accept a process-local checkpointer."
)

_NO_TELEGRAM_TOKEN_ERROR = (
    "TELEGRAM_BOT_TOKEN is not set and APP_ENV is not 'development'. Telegram is the only "
    "outbound channel, so every Watchdog alert, briefing notice, scenario match and Sentinel "
    "broadcast would be logged and silently dropped. Set TELEGRAM_BOT_TOKEN for this "
    "environment, or set APP_ENV=development to accept log-only delivery."
)


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
        # ONE shared httpx client pooled across every external HTTP provider (issue #71) —
        # see `get_http_client`; closed on shutdown via `aclose_http_client`.
        self._http_client: httpx.AsyncClient | None = None
        # Two LLM provider instances, one per tier (issue #28) — see `get_fast_llm_provider`.
        self._fast_llm_provider: LLMProvider | None = None
        self._reasoning_llm_provider: LLMProvider | None = None
        self._freshness_policy: FreshnessPolicy | None = None
        self._sentiment_repository: SentimentRepository | None = None
        self._refresh_tracked_analysis_use_case: RefreshTrackedAnalysis | None = None
        self._tts_provider: TTSProvider | None = None
        self._stt_provider: STTProvider | None = None
        self._embedding_provider: EmbeddingProvider | None = None
        self._vector_store: VectorStore | None = None
        self._agent_memory: AgentMemory | None = None
        self._conversation_repository: ConversationRepository | None = None
        self._watchlist_repository: WatchlistRepository | None = None
        self._reorder_watchlists_use_case: ReorderWatchlists | None = None
        self._note_repository: NoteRepository | None = None
        self._user_profile_repository: UserProfileRepository | None = None
        self._resolve_locale_use_case: ResolveLocale | None = None
        self._signal_repository: SignalRepository | None = None
        self._briefing_repository: BriefingRepository | None = None
        self._news_provider: NewsProvider | None = None
        self._news_item_repository: NewsItemRepository | None = None
        self._instrument_catalog_repository: InstrumentCatalogRepository | None = None
        self._instrument_universe: SupabaseInstrumentUniverse | None = None
        self._coingecko_key_ring: CoinGeckoKeyRing | None = None
        self._coingecko_search_provider: CoinGeckoSearchProvider | None = None
        self._search_coins_use_case: SearchCoins | None = None
        self._register_instrument_use_case: RegisterInstrument | None = None
        self._instrument_metadata_provider: InstrumentMetadataProvider | None = None
        self._market_data_provider: MarketDataProvider | None = None
        self._macro_data_provider: MacroDataProvider | None = None
        self._fundamentals_provider: FundamentalsProvider | None = None
        # Two chat models: cheap router, stronger specialists (issue #28).
        self._router_chat_model: BaseChatModel | None = None
        self._specialist_chat_model: BaseChatModel | None = None
        self._chat_graph: Any | None = None
        self._agent_runner: AgentRunner | None = None
        self._realtime_session_provider: RealtimeSessionProvider | None = None
        self._generate_consequence_chain_use_case: GenerateConsequenceChain | None = None
        self._generate_conversation_title_use_case: GenerateConversationTitle | None = None
        self._notification_channel: NotificationChannel | None = None
        self._alerted_signal_tracker: AlertedSignalTracker | None = None
        self._news_feed_refresher: NewsFeedRefresher | None = None
        self._telegram_link_repository: TelegramLinkRepository | None = None
        self._telegram_link_token_repository: TelegramLinkTokenRepository | None = None
        self._telegram_messenger: TelegramMessenger | None = None
        self._link_telegram_account_use_case: LinkTelegramAccount | None = None
        self._scenario_repository: ScenarioRepository | None = None
        self._scenario_simulation_runner: ScenarioSimulationRunner | None = None
        self._briefing_command_handler: BriefingCommandHandler | None = None
        self._signal_command_handler: SignalCommandHandler | None = None
        self._simulate_command_handler: SimulateCommandHandler | None = None
        self._impact_command_handler: ImpactCommandHandler | None = None
        self._chat_message_handler: ChatMessageHandler | None = None
        self._briefing_document_renderer: BriefingDocumentRenderer | None = None
        self._email_sender: EmailSender | None = None
        self._fear_greed_provider: FearGreedProvider | None = None
        self._analyze_sentiment_use_case: AnalyzeSentiment | None = None
        self._interpret_macro_event_use_case: InterpretMacroEvent | None = None
        self._event_analyzer: EventAnalyzerPort | None = None
        self._event_repository: EventRepositoryPort | None = None
        self._event_news_provider: NewsProviderPort | None = None
        self._process_incoming_event_use_case: ProcessIncomingEvent | None = None
        self._processed_event_tracker: ProcessedEventTracker | None = None
        self._broadcast_important_events_use_case: BroadcastImportantEvents | None = None
        self._event_callback_handler: EventCallbackHandler | None = None
        self._chart_config: ChartConfig | None = None
        self._build_price_chart_use_case: BuildPriceChart | None = None
        self._build_comparison_chart_use_case: BuildComparisonChart | None = None
        self._build_drawdown_chart_use_case: BuildDrawdownChart | None = None
        self._build_distribution_chart_use_case: BuildDistributionChart | None = None
        self._build_macro_chart_use_case: BuildMacroChart | None = None
        self._build_sentiment_gauge_use_case: BuildSentimentGauge | None = None
        self._render_chart_use_case: RenderChart | None = None

    def get_fast_llm_provider(self) -> LLMProvider:
        """Return the cached FAST-tier `LLMProvider` (`settings.openai_model`) — issue #28.

        Backs the call sites that are structured, tiny, and already correct on a cheap model:
        conversation titling, sentiment tone scoring, scenario intake extraction, and news
        blurb localization. There is no generic `get_llm_provider()` any more, on purpose: an
        un-suffixed accessor is exactly how a reasoning-tier call site silently drifts onto the
        cheap model (or the reverse, quietly multiplying its bill). Every caller now has to
        state which tier it wants, and pyright catches anyone who forgets.
        """
        if self._fast_llm_provider is None:
            self._fast_llm_provider = OpenAIProvider(
                api_key=self._settings.openai_api_key, model=self._settings.openai_model
            )
        return self._fast_llm_provider

    def get_reasoning_llm_provider(self) -> LLMProvider:
        """Return the cached REASONING-tier `LLMProvider` (`settings.reasoning_model`) — #28.

        Backs the multi-step analytical calls that are the product's actual value and the ones
        most likely to be under-served by `mini`: impact signals, pending-news batch analysis,
        scenario synthesis, causal consequence chains, macro event interpretation, and
        watchlist briefings.

        `settings.reasoning_model` falls back to `openai_model` when `OPENAI_MODEL_REASONING`
        is unset, so this is a SEPARATE INSTANCE but the SAME model until an operator configures
        a stronger one — i.e. the tiering wiring changes no behavior on its own. The no-API-key
        guard is unchanged: `OpenAIProvider` still degrades to its placeholder on both tiers.
        """
        if self._reasoning_llm_provider is None:
            self._reasoning_llm_provider = OpenAIProvider(
                api_key=self._settings.openai_api_key, model=self._settings.reasoning_model
            )
        return self._reasoning_llm_provider

    def get_freshness_policy(self) -> FreshnessPolicy:
        """Return the cached `FreshnessPolicy` — how long shared analysis stays cacheable (#29).

        THE place the asset-class TTL map is assembled from `Settings`. `CREDIT` and `COMMODITY`
        deliberately get no dedicated bucket and fall through to `default_ttl`, as does any
        analysis with no instrument behind it (a preset scenario run).
        """
        if self._freshness_policy is None:
            self._freshness_policy = FreshnessPolicy(
                ttl_by_asset_class={
                    AssetClass.CRYPTO: timedelta(
                        minutes=self._settings.analysis_ttl_crypto_minutes
                    ),
                    AssetClass.STOCK: timedelta(minutes=self._settings.analysis_ttl_equity_minutes),
                    AssetClass.FOREX: timedelta(minutes=self._settings.analysis_ttl_fx_minutes),
                },
                default_ttl=timedelta(minutes=self._settings.analysis_ttl_default_minutes),
            )
        return self._freshness_policy

    def get_sentiment_repository(self) -> SentimentRepository:
        if self._sentiment_repository is None:
            self._sentiment_repository = SupabaseSentimentRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._sentiment_repository

    def get_tts_provider(self) -> TTSProvider | None:
        """Return the cached `TTSProvider`, or `None` when TTS isn't both enabled AND
        keyed.

        `None` (not an exception) is the contract here — same graceful-degradation
        pattern as `get_notification_channel`/`get_telegram_messenger`: the
        `POST /api/v1/chat/speak` endpoint turns `None` into a 503 and the frontend
        falls back to the browser's built-in speech synthesis, so chat keeps working
        without a TTS key. Uses its own `tts_api_key` (not `openai_api_key`) so TTS is
        enabled/billed independently of the chat/embedding pipelines.
        """
        if self._tts_provider is None and self._settings.tts_enabled and self._settings.tts_api_key:
            self._tts_provider = OpenAITTSProvider(
                api_key=self._settings.tts_api_key, model=self._settings.tts_model
            )
        return self._tts_provider

    def get_stt_provider(self) -> STTProvider | None:
        """Return the cached `STTProvider`, or `None` when STT isn't both enabled AND
        keyed.

        Mirror image of `get_tts_provider`: `None` (not an exception) is the contract —
        the `POST /api/v1/chat/transcribe` endpoint turns `None` into a 503 and the
        frontend falls back to the browser's built-in speech recognition, so chat keeps
        working without an STT key. Uses its own `stt_api_key` (not `openai_api_key`) so
        STT is enabled/billed independently of the chat/embedding pipelines.
        """
        if self._stt_provider is None and self._settings.stt_enabled and self._settings.stt_api_key:
            self._stt_provider = OpenAISTTProvider(
                api_key=self._settings.stt_api_key, model=self._settings.stt_model
            )
        return self._stt_provider

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

    def get_http_client(self) -> httpx.AsyncClient:
        """Return the ONE shared `httpx.AsyncClient` reused by every external HTTP provider.

        A single client is a single connection pool + TLS session cache shared across all
        outbound calls (Marketaux, FRED, alternative.me, CoinGecko), so each request reuses a
        warm keep-alive connection instead of paying a fresh pool setup and TLS handshake
        (~50-300ms) per call — the fix for every provider opening `async with
        httpx.AsyncClient(...)` per request (issue #71).

        Deliberately built with NO `base_url` and NO default timeout: it is shared across
        providers that each target a different host and already pass their own
        `Settings`-derived per-request timeout, so those stay at the call sites (each provider
        threads `timeout=` into its `client.get(...)`). Lazily built and cached like every other
        adapter here; released on shutdown by `aclose_http_client` (see `main.py`'s lifespan).
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def initialize_agent_memory(self) -> None:
        """Build and cache the DURABLE agent checkpointer at startup — never crash boot.

        Postgres (`DATABASE_URL`) is now the primary durable checkpointer and the only one
        that actually works under `graph.astream`: `AsyncPostgresSaver` implements the async
        `aget_tuple`/`aput` the async runner awaits, which the sync `RedisSaver` does not
        (it inherits them as `raise NotImplementedError`). Must be awaited once during app
        startup (`main.py`'s `_lifespan`), before the first chat builds the graph.

        Failure handling mirrors `_warn_on_misconfigured_auth`'s "log loudly, don't crash":

        - **`DATABASE_URL` set but the checkpointer fails to initialize.** A transient/infra
          fault, not a config error — degrade to `InMemoryCheckpointer` rather than crash.
          In development that's a warning; anywhere else it's a CRITICAL log stating that
          agent memory is now per-process and not shared across replicas, because the
          durable store the operator asked for is silently unavailable.

        - **No `DATABASE_URL`, but `REDIS_URL` set.** Fall back to the legacy Redis probe
          path, with a warning that the sync `RedisSaver` is incompatible with `astream`.

        - **Neither configured.** Current behavior: in-memory in development, otherwise a
          hard error — nothing durable is configured at all, which is a misconfiguration to
          surface, not a mode to run in.
        """
        if self._settings.database_url:
            postgres_memory = PostgresCheckpointer(database_url=self._settings.database_url)
            try:
                await postgres_memory.initialize()
            except Exception:  # noqa: BLE001 — an infra fault degrades, never crashes boot
                self._agent_memory = self._fallback_in_memory_on_postgres_failure()
            else:
                self._agent_memory = postgres_memory
            return

        if self._settings.redis_url:
            logging.getLogger(__name__).warning(
                "DATABASE_URL is not set; using the legacy Redis checkpointer. The sync "
                "RedisSaver leaves the async checkpoint methods unimplemented, so on a "
                "module-capable (RediSearch/RedisJSON) Redis every astream chat turn will "
                "error — prefer DATABASE_URL for durable, astream-compatible agent memory."
            )
        self._agent_memory = self._select_legacy_agent_memory()

    def _fallback_in_memory_on_postgres_failure(self) -> InMemoryCheckpointer:
        """Log the Postgres-checkpointer failure per environment, return an in-memory saver.

        Development gets a warning; anywhere else a CRITICAL, because falling back means the
        durable store the operator configured is silently gone and agent memory is now
        per-process and lost on restart — the loud-log-not-crash stance of
        `_warn_on_misconfigured_auth`.
        """
        log = logging.getLogger(__name__)
        if self._settings.app_env == "development":
            log.warning(
                "DATABASE_URL is set but the Postgres agent checkpointer failed to "
                "initialize; falling back to InMemoryCheckpointer. Agent memory is "
                "process-local and will not survive a restart.",
                exc_info=True,
            )
        else:
            log.critical(
                "DATABASE_URL is set but the Postgres agent checkpointer failed to "
                "initialize. Falling back to InMemoryCheckpointer: agent memory is now "
                "PER-PROCESS, lost on restart, and NOT shared across replicas. Fix the "
                "database connection to restore durable agent memory.",
                exc_info=True,
            )
        return InMemoryCheckpointer()

    def _select_legacy_agent_memory(self) -> AgentMemory:
        """Pre-Postgres checkpointer selection: legacy Redis probe, else dev in-memory, else raise.

        Unchanged from the original `get_agent_memory` body. Reused by the synchronous
        accessor (for non-lifespan paths such as unit tests) and by
        `initialize_agent_memory`'s no-`DATABASE_URL` branch, so both keep the exact old
        behavior. See `initialize_agent_memory` for why Postgres is now preferred.
        """
        if self._settings.redis_url:
            redis_memory = RedisCheckpointer(redis_url=self._settings.redis_url)
            try:
                redis_memory.get_checkpointer()  # probe: connects + creates indices
                return redis_memory
            except Exception:  # noqa: BLE001 — a reachability fault degrades, never breaks
                logging.getLogger(__name__).warning(
                    "REDIS_URL is set but the Redis checkpointer failed to "
                    "initialize; falling back to InMemoryCheckpointer",
                    exc_info=True,
                )
                return InMemoryCheckpointer()
        if self._settings.app_env == "development":
            logging.getLogger(__name__).warning(
                "REDIS_URL is not set; using InMemoryCheckpointer. Agent memory is "
                "process-local and will not survive a restart."
            )
            return InMemoryCheckpointer()
        raise RuntimeError(_NO_REDIS_URL_ERROR)

    def get_agent_memory(self) -> AgentMemory:
        """Return the agent checkpointer, preferring the durable one built at startup.

        When `initialize_agent_memory()` ran (the normal path in `main.py`'s lifespan),
        `self._agent_memory` is already the durable Postgres checkpointer (or the in-memory
        fallback it chose), and this just returns it.

        This synchronous accessor is the FALLBACK for code paths that never ran the lifespan
        (unit tests, direct construction): it keeps the pre-Postgres selection — the legacy
        Redis probe, else a dev-only in-memory saver, else a hard error outside development.
        It deliberately does NOT build the Postgres checkpointer, which needs an async
        `initialize()`; `initialize_agent_memory()` is the only place that does.

        Note the two stores are not redundant: this one is the agent's working memory for a
        thread; `conversations` is the durable record of what was said.
        """
        if self._agent_memory is None:
            self._agent_memory = self._select_legacy_agent_memory()
        return self._agent_memory

    async def aclose_agent_memory(self) -> None:
        """Close the agent checkpointer's resources on shutdown (guarded, best-effort).

        Only `PostgresCheckpointer` holds a connection pool to release; the in-memory and
        Redis savers have nothing to close, so this no-ops for them.
        """
        if isinstance(self._agent_memory, PostgresCheckpointer):
            await self._agent_memory.aclose()

    async def aclose_http_client(self) -> None:
        """Close the shared httpx client's connection pool on shutdown (guarded, best-effort).

        No-ops when the client was never built (no external HTTP provider was used this run).
        Mirrors `aclose_agent_memory`; both are awaited from `main.py`'s lifespan `finally`.
        """
        if self._http_client is not None:
            await self._http_client.aclose()

    def get_conversation_repository(self) -> ConversationRepository:
        """Return the cached Supabase-backed conversation store (durable chat history).

        This used to hand back a stub whose `save()` wrote into an in-process dict, which is
        why chat history never reached the database. It is now a real `supabase-py` adapter
        against `conversations` / `conversation_messages` (migration 0020), wired with the
        same retry settings as every other per-user repository.
        """
        if self._conversation_repository is None:
            self._conversation_repository = SupabaseConversationRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._conversation_repository

    def get_watchlist_repository(self) -> WatchlistRepository:
        if self._watchlist_repository is None:
            self._watchlist_repository = SupabaseWatchlistRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._watchlist_repository

    def get_reorder_watchlists_use_case(self) -> ReorderWatchlists:
        """Return the cached `ReorderWatchlists` use case (issue #66).

        Backs `PATCH /api/v1/watchlists/reorder`. Only depends on the watchlist
        repository, so caching one instance is safe — same shape as the other
        single-port use cases wired here.
        """
        if self._reorder_watchlists_use_case is None:
            self._reorder_watchlists_use_case = ReorderWatchlists(
                watchlist_repository=self.get_watchlist_repository()
            )
        return self._reorder_watchlists_use_case

    def get_note_repository(self) -> NoteRepository:
        """Return Supabase notes, with process-local storage for unconfigured development."""
        if self._note_repository is None:
            supabase_configured = bool(self._settings.supabase_url and self._settings.supabase_key)
            if self._settings.app_env == "development" and not supabase_configured:
                logging.getLogger(__name__).warning(
                    "Supabase notes are not configured; using process-local development storage."
                )
                self._note_repository = InMemoryNoteRepository()
            else:
                self._note_repository = SupabaseNoteRepository(
                    supabase_url=self._settings.supabase_url,
                    supabase_key=self._settings.supabase_key,
                    retry_max_attempts=self._settings.supabase_retry_max_attempts,
                    retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
                )
        return self._note_repository

    def get_user_profile_repository(self) -> UserProfileRepository:
        """Return the cached per-user UserProfileRepository (issue #67), Supabase-backed with
        the same retry/config wiring as the other per-user repositories."""
        if self._user_profile_repository is None:
            self._user_profile_repository = SupabaseUserProfileRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._user_profile_repository

    def get_resolve_locale_use_case(self) -> ResolveLocale:
        """Return the cached `ResolveLocale` use case (issue #67).

        The single place that answers "what language does this reply go out in":
        request locale -> the user's stored `preferred_locale` -> `Settings.default_locale`.
        Only depends on one repository plus a settings value, so caching one instance is
        safe — same shape as the other single-port use cases wired here.
        """
        if self._resolve_locale_use_case is None:
            self._resolve_locale_use_case = ResolveLocale(
                user_profile_repository=self.get_user_profile_repository(),
                default_locale=self._settings.default_locale,
            )
        return self._resolve_locale_use_case

    def get_signal_repository(self) -> SignalRepository:
        if self._signal_repository is None:
            self._signal_repository = SupabaseSignalRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._signal_repository

    def get_news_item_repository(self) -> NewsItemRepository:
        """Return the cached NewsItemRepository (issue #1's persisted news store)."""
        if self._news_item_repository is None:
            self._news_item_repository = SupabaseNewsItemRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                sentiment_neutral_threshold=self._settings.news_sentiment_neutral_threshold,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._news_item_repository

    def get_briefing_repository(self) -> BriefingRepository:
        if self._briefing_repository is None:
            self._briefing_repository = SupabaseBriefingRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._briefing_repository

    def get_briefing_document_renderer(self) -> BriefingDocumentRenderer:
        """Return the cached PDF renderer for briefing export (issue #22).

        `ReportLabBriefingPdfRenderer` is the only adapter — see its docstring for why
        `reportlab` was chosen over `weasyprint` in this sandbox.
        """
        if self._briefing_document_renderer is None:
            self._briefing_document_renderer = ReportLabBriefingPdfRenderer()
        return self._briefing_document_renderer

    def get_email_sender(self) -> EmailSender:
        """Return the cached `EmailSender` for briefing export's "send by email" path.

        Always `LoggingEmailSender` today — no real SMTP/email-service integration is
        wired yet (see that adapter's docstring for why this is a deliberate scope
        decision, not an oversight). Swap this method to gate on a future `Settings`
        field (e.g. an SES/SendGrid API key) once a real adapter lands, same
        "unconfigured -> logging fallback" pattern as `get_notification_channel`'s
        Telegram gate.
        """
        if self._email_sender is None:
            self._email_sender = LoggingEmailSender()
        return self._email_sender

    def get_notification_channel(self) -> NotificationChannel:
        """Return the cached Watchdog alert delivery channel.

        `TelegramNotificationChannel` when `TELEGRAM_BOT_TOKEN` is configured (issue #14) —
        it delivers over the ONE shared bot, resolving each recipient's chat through
        `telegram_links`.

        With no token there is no bot to deliver through, and what happens next now depends
        on the environment. In development the fallback is `LoggingNotificationChannel`,
        which composes the notification and logs it instead of sending, so Watchdog stays
        demo-able end to end without a Telegram integration. Anywhere else, a missing token
        RAISES.

        That used to be an ungated fallback, and it was the most dangerous silent failure in
        the container: Telegram is this product's entire outbound channel, so a deploy that
        forgot `TELEGRAM_BOT_TOKEN` swallowed every Watchdog alert, briefing-ready notice,
        scenario match and Sentinel broadcast — the system looked healthy, the scheduler
        reported success, and no user heard anything. Refusing to start is the only honest
        response to "I have no way to deliver the thing I exist to deliver".

        Nothing in `application/` or `api/` needs to know which adapter is behind the port.
        """
        if self._notification_channel is None:
            messenger = self.get_telegram_messenger()
            if messenger is not None:
                self._notification_channel = TelegramNotificationChannel(
                    messenger=messenger,
                    watchlist_repository=self.get_watchlist_repository(),
                    telegram_link_repository=self.get_telegram_link_repository(),
                    frontend_base_url=self._settings.frontend_base_url,
                )
            elif self._settings.app_env == "development":
                logging.getLogger(__name__).warning(
                    "TELEGRAM_BOT_TOKEN is not set; using LoggingNotificationChannel. "
                    "Alerts will be composed and logged, never delivered."
                )
                self._notification_channel = LoggingNotificationChannel()
            else:
                raise RuntimeError(_NO_TELEGRAM_TOKEN_ERROR)
        return self._notification_channel

    def get_alerted_signal_tracker(self) -> AlertedSignalTracker:
        """Return the cached, process-wide `AlertedSignalTracker` singleton.

        Shared between the scheduler's periodic Watchdog scan job and the manual
        "Scan now" endpoint so both draw from the same in-process novelty/dedup state —
        see `AlertedSignalTracker`'s docstring for why this isn't persisted.
        """
        if self._alerted_signal_tracker is None:
            self._alerted_signal_tracker = AlertedSignalTracker(
                cooldown=timedelta(minutes=self._settings.watchdog_alert_cooldown_minutes)
            )
        return self._alerted_signal_tracker

    def get_news_feed_refresher(self) -> NewsFeedRefresher:
        """Return the cached, process-wide `NewsFeedRefresher` singleton (taws#71).

        Must be a singleton: its in-flight/throttle state is the only thing keeping the
        radar's polling clients from stampeding the upstream news providers now that
        `GET /api/v1/news` schedules a refresh on every served request.
        """
        if self._news_feed_refresher is None:
            self._news_feed_refresher = NewsFeedRefresher(
                ingest_news=IngestNews(
                    news_provider=self.get_news_provider(),
                    news_item_repository=self.get_news_item_repository(),
                    signal_repository=self.get_signal_repository(),
                ),
                min_interval_seconds=self._settings.news_refresh_min_interval_seconds,
                limit=self._settings.news_refresh_limit,
            )
        return self._news_feed_refresher

    def get_telegram_link_repository(self) -> TelegramLinkRepository:
        if self._telegram_link_repository is None:
            self._telegram_link_repository = SupabaseTelegramLinkRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._telegram_link_repository

    def get_telegram_link_token_repository(self) -> TelegramLinkTokenRepository:
        if self._telegram_link_token_repository is None:
            self._telegram_link_token_repository = SupabaseTelegramLinkTokenRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._telegram_link_token_repository

    def get_telegram_messenger(self) -> TelegramMessenger | None:
        """Return the cached `TelegramMessenger`, or `None` when `TELEGRAM_BOT_TOKEN` isn't
        configured. `None` (not an exception) is the contract here — callers (
        `get_notification_channel`, `get_link_telegram_account_use_case`) each apply their
        own fallback, same unconfigured-integration pattern used across this `Container`.
        """
        if self._telegram_messenger is None and self._settings.telegram_bot_token:
            self._telegram_messenger = TelegramBotClient(
                bot_token=self._settings.telegram_bot_token
            )
        return self._telegram_messenger

    def get_link_telegram_account_use_case(self) -> LinkTelegramAccount | None:
        """Return the cached `LinkTelegramAccount` use case, or `None` when Telegram isn't
        configured — the webhook router acks Telegram with 200 either way (see
        `api/v1/routers/telegram.py`), it just can't complete a link without a messenger.
        """
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._link_telegram_account_use_case is None:
            self._link_telegram_account_use_case = LinkTelegramAccount(
                token_repository=self.get_telegram_link_token_repository(),
                link_repository=self.get_telegram_link_repository(),
                messenger=messenger,
            )
        return self._link_telegram_account_use_case

    # -- Telegram inbound-command handlers -------------------------------------------------
    #
    # There is exactly ONE bot now (the shared `.env` bot users link to via
    # `/telegram/link-token` -> `https://t.me/<bot>?start=<token>`), so there is exactly one
    # messenger. The per-user BotFather registration flow -- and the `/telegram/webhook/{bot_id}`
    # route that needed a handler bound to each registered bot's own token -- is gone.
    #
    # `build_*_command_handler(messenger)` -- NOT cached. Builds a handler replying through the
    # messenger you pass; a handler answers via `messenger.send_text(...)`, so the messenger it
    # holds IS the identity the reply comes from. Kept as the construction seam the cached
    # accessors below are built on (and the injection point tests use).
    #
    # `get_*_command_handler()` -- cached, bound to the shared bot's messenger. This is what the
    # `/telegram/webhook` route uses.

    def build_briefing_command_handler(
        self, messenger: TelegramMessenger
    ) -> BriefingCommandHandler:
        """A `/briefing` handler replying through `messenger`. See the note above."""
        return BriefingCommandHandler(
            link_repository=self.get_telegram_link_repository(),
            watchlist_repository=self.get_watchlist_repository(),
            briefing_repository=self.get_briefing_repository(),
            messenger=messenger,
            frontend_base_url=self._settings.frontend_base_url,
        )

    def build_signal_command_handler(self, messenger: TelegramMessenger) -> SignalCommandHandler:
        """A `/signal <TICKER>` handler replying through `messenger`. See the note above."""
        return SignalCommandHandler(
            link_repository=self.get_telegram_link_repository(),
            instrument_universe=self.get_instrument_universe(),
            signal_repository=self.get_signal_repository(),
            messenger=messenger,
        )

    def build_simulate_command_handler(
        self, messenger: TelegramMessenger
    ) -> SimulateCommandHandler:
        """A `/simular <text>` handler replying through `messenger`. Reuses the same cached
        `ScenarioSimulationRunner` as `POST /api/v1/scenarios/generate` and the
        `run_scenario_simulation` chat tool — see `get_scenario_simulation_runner`."""
        return SimulateCommandHandler(
            link_repository=self.get_telegram_link_repository(),
            scenario_simulation_runner=self.get_scenario_simulation_runner(),
            messenger=messenger,
            frontend_base_url=self._settings.frontend_base_url,
            default_locale=self._settings.default_locale,
        )

    def build_impact_command_handler(self, messenger: TelegramMessenger) -> ImpactCommandHandler:
        """An `/impact <sector>` handler replying through `messenger`. See the note above."""
        return ImpactCommandHandler(
            event_repository=self.get_event_repository(),
            analyze_event_impact=AnalyzeEventImpact(analyzer=self.get_event_analyzer()),
            messenger=messenger,
        )

    def build_chat_message_handler(self, messenger: TelegramMessenger) -> ChatMessageHandler:
        """A conversational handler replying through `messenger`. See the note above.

        Telegram has no per-user language preference of its own, so the handler answers in
        `Settings.default_locale` (issue #67) rather than defaulting to the personas' English.
        """
        return ChatMessageHandler(
            agent_runner=self.get_agent_runner(),
            messenger=messenger,
            default_locale=self._settings.default_locale,
        )

    def get_briefing_command_handler(self) -> BriefingCommandHandler | None:
        """Return the main bot's cached `/briefing` handler, or `None` when Telegram isn't
        configured — same unconfigured-integration fallback shape as
        `get_link_telegram_account_use_case` (issue #19).
        """
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._briefing_command_handler is None:
            self._briefing_command_handler = self.build_briefing_command_handler(messenger)
        return self._briefing_command_handler

    def get_signal_command_handler(self) -> SignalCommandHandler | None:
        """Return the main bot's cached `/signal <TICKER>` handler, or `None` when
        Telegram isn't configured (issue #19)."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._signal_command_handler is None:
            self._signal_command_handler = self.build_signal_command_handler(messenger)
        return self._signal_command_handler

    def get_simulate_command_handler(self) -> SimulateCommandHandler | None:
        """Return the main bot's cached `/simular <text>` handler, or `None` when
        Telegram isn't configured (issue #19)."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._simulate_command_handler is None:
            self._simulate_command_handler = self.build_simulate_command_handler(messenger)
        return self._simulate_command_handler

    def get_impact_command_handler(self) -> ImpactCommandHandler | None:
        """Return the main bot's cached `/impact <sector>` handler, or `None` when
        Telegram isn't configured — same pattern as `get_briefing_command_handler`."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._impact_command_handler is None:
            self._impact_command_handler = self.build_impact_command_handler(messenger)
        return self._impact_command_handler

    def get_chat_message_handler(self) -> ChatMessageHandler | None:
        """Return the main bot's cached conversational handler, or `None` when Telegram
        isn't configured — same pattern as `get_briefing_command_handler`."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._chat_message_handler is None:
            self._chat_message_handler = self.build_chat_message_handler(messenger)
        return self._chat_message_handler

    def get_news_provider(self) -> NewsProvider:
        """Return the aggregated news source for the radar/agents.

        Fans out to every configured live source (Marketaux, NewsAPI, Finnhub, RSS, SEC
        EDGAR filings) concurrently; a source with no API key configured (or, for EDGAR,
        disabled/no feed URLs configured) is left out of the fan-out entirely.

        No fixture fallback: with no source configured, or with every source failing, this
        raises `NewsUnavailableError` rather than serving canned articles with `example.com`
        URLs as if they were reporting. See `AggregatingNewsProvider` for the merge/dedupe/
        link/filter pipeline.
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
                        cooldown_seconds=self._settings.marketaux_cooldown_minutes * 60,
                        rate_limit_cooldown_seconds=(
                            self._settings.marketaux_rate_limit_cooldown_minutes * 60
                        ),
                        http_client=self.get_http_client(),
                    )
                )
            if self._settings.newsapi_api_key:
                live_providers.append(
                    NewsApiNewsProvider(
                        api_key=self._settings.newsapi_api_key,
                        base_url=self._settings.newsapi_base_url,
                        default_query=self._settings.newsapi_default_query,
                        cooldown_seconds=self._settings.newsapi_cooldown_minutes * 60,
                        rate_limit_cooldown_seconds=(
                            self._settings.newsapi_rate_limit_cooldown_minutes * 60
                        ),
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
                live_providers.append(
                    RssNewsProvider(
                        feed_urls=self._settings.rss_feed_urls,
                        timeout_seconds=self._settings.rss_feed_timeout_seconds,
                    )
                )
            # SEC EDGAR filings (issue #21): free, no API key required, but gated by its
            # own feature flag (`sec_edgar_enabled`, default on) so it can be turned off
            # independently of RSS without clearing `sec_edgar_feed_urls`.
            if self._settings.sec_edgar_enabled and self._settings.sec_edgar_feed_urls:
                live_providers.append(
                    SecEdgarNewsProvider(
                        feed_urls=self._settings.sec_edgar_feed_urls,
                        user_agent=self._settings.sec_edgar_user_agent,
                        timeout_seconds=self._settings.sec_edgar_feed_timeout_seconds,
                    )
                )

            has_vendor_news_keys = bool(
                self._settings.marketaux_api_key
                or self._settings.newsapi_api_key
                or self._settings.finnhub_api_key
            )
            if self._settings.app_env == "development" and not has_vendor_news_keys:
                # RSS/Yahoo and SEC EDGAR often stall on local networks; fixture data
                # is enough for the hackathon UI when no paid news keys are configured.
                live_providers = []

            self._news_provider = AggregatingNewsProvider(
                providers=live_providers,
                instrument_universe=self.get_instrument_universe(),
                provider_timeout_seconds=self._settings.news_provider_timeout_seconds,
                live_fetch_budget_seconds=self._settings.news_live_fetch_budget_seconds,
            )
        return self._news_provider

    def get_instrument_catalog_repository(self) -> InstrumentCatalogRepository:
        if self._instrument_catalog_repository is None:
            self._instrument_catalog_repository = SupabaseInstrumentCatalogRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._instrument_catalog_repository

    async def build_instrument_universe(self) -> InstrumentUniverse:
        """Load `public.instruments` once and cache the resulting universe singleton.

        MUST be awaited during app startup (`main.py`'s `_lifespan`, before other
        warmup) — `get_instrument_universe()` only returns the already-built
        instance and never constructs it lazily itself (design decision #1: the
        `InstrumentUniverse` port stays sync, so the one async DB read happens here,
        not on the request path).
        """
        repo = self.get_instrument_catalog_repository()
        self._instrument_universe = await SupabaseInstrumentUniverse.create(repo)
        return self._instrument_universe

    def get_instrument_universe(self) -> InstrumentUniverse:
        if self._instrument_universe is None:
            raise RuntimeError(
                "InstrumentUniverse was not built yet — `build_instrument_universe()` "
                "must be awaited during app startup before this accessor is used."
            )
        return self._instrument_universe

    def get_coingecko_key_ring(self) -> CoinGeckoKeyRing:
        """Return the ONE CoinGecko key ring shared by every CoinGecko adapter.

        Sharing is the whole point, not an optimization: CoinGecko meters its Demo quota per
        key, and prices, `/coins/markets` metadata, and `/search` all spend that same key. One
        ring means a 429 discovered while fetching prices immediately steers the metadata and
        search calls off the exhausted key too, instead of each adapter having to burn its own
        request to rediscover the rate limit.
        """
        if self._coingecko_key_ring is None:
            self._coingecko_key_ring = CoinGeckoKeyRing(
                api_keys=self._settings.coingecko_api_keys,
                key_cooldown_seconds=self._settings.coingecko_key_cooldown_seconds,
            )
        return self._coingecko_key_ring

    def get_coingecko_search_provider(self) -> CoinGeckoSearchProvider:
        """Return the cached CoinGecko `/search` adapter (issue #60 candidate resolution).

        Reuses the same base URL, key ring, and cooldown settings as
        `get_market_data_provider`'s `CoinGeckoMarketDataProvider` — same vendor, same
        graceful rate-limit degradation (429/timeout -> `[]`, see
        `CoinGeckoCoinSearchProvider`'s docstring), just a different endpoint.
        """
        if self._coingecko_search_provider is None:
            self._coingecko_search_provider = CoinGeckoCoinSearchProvider(
                base_url=self._settings.coingecko_base_url,
                key_ring=self.get_coingecko_key_ring(),
                cooldown_seconds=self._settings.coingecko_cooldown_seconds,
                http_client=self.get_http_client(),
            )
        return self._coingecko_search_provider

    def get_search_coins_use_case(self) -> SearchCoins:
        """Return the cached `SearchCoins` use case backing `GET /instruments/search`."""
        if self._search_coins_use_case is None:
            self._search_coins_use_case = SearchCoins(
                search_provider=self.get_coingecko_search_provider()
            )
        return self._search_coins_use_case

    def get_register_instrument_use_case(self) -> RegisterInstrument:
        """Return the cached `RegisterInstrument` use case backing `POST /instruments`.

        Depends on the domain `MutableInstrumentUniverse` protocol (design's FIX #6)
        via the same `InstrumentUniverse` singleton every other pipeline uses —
        `SupabaseInstrumentUniverse.add()` satisfies it structurally.
        """
        if self._register_instrument_use_case is None:
            self._register_instrument_use_case = RegisterInstrument(
                catalog_repository=self.get_instrument_catalog_repository(),
                universe=self.get_instrument_universe(),
                watchlist_repository=self.get_watchlist_repository(),
            )
        return self._register_instrument_use_case

    def get_list_enriched_instruments_use_case(self) -> ListEnrichedInstruments:
        """Build the enriched-universe listing pipeline (explorer rows + highlights).

        NOT cached: like `get_generate_signal_use_case`, it is a thin orchestrator over
        collaborators that are themselves cached singletons. THE single construction site —
        `GET /instruments/enriched` (via `api/v1/dependencies/`) and the chat agents'
        `get_market_movers` tool both resolve it from here, so the explorer page and the
        agent can never disagree about how the leaderboards are computed.
        """
        return ListEnrichedInstruments(
            instrument_universe=self.get_instrument_universe(),
            market_data_provider=self.get_market_data_provider(),
            signal_repository=self.get_signal_repository(),
            instrument_metadata_provider=self.get_instrument_metadata_provider(),
        )

    def get_news_prefilter_policy(self) -> NewsPrefilterPolicy:
        """Return the Analyst pre-filter's gate tuning (issue #26), assembled from `Settings`.

        The single place these `news_*` settings are read. Both callers of
        `AnalyzePendingNews` — `POST /api/v1/news/analyze-pending` and the scheduled tick —
        resolve the policy from here, so an operator retuning the gate can't end up with the
        endpoint and the background job disagreeing about what gets classified.
        """
        settings = self._settings
        return NewsPrefilterPolicy(
            skip_threshold=settings.news_relevance_skip_threshold,
            relevance_weight=settings.news_prefilter_relevance_weight,
            materiality_weight=settings.news_prefilter_materiality_weight,
            name_match_score=settings.news_relevance_name_match_score,
            materiality_keywords=tuple(settings.news_materiality_keywords),
            materiality_high_impact_sources=tuple(settings.news_materiality_high_impact_sources),
            materiality_keyword_weight=settings.news_materiality_keyword_weight,
            materiality_source_weight=settings.news_materiality_source_weight,
            materiality_sentiment_weight=settings.news_materiality_sentiment_weight,
            materiality_recency_weight=settings.news_materiality_recency_weight,
            materiality_recency_half_life_hours=(settings.news_materiality_recency_half_life_hours),
            materiality_keyword_saturation_count=(
                settings.news_materiality_keyword_saturation_count
            ),
        )

    def get_market_data_provider(self) -> MarketDataProvider:
        """Return the routing MarketDataProvider (CoinGecko for crypto, yfinance otherwise).

        There is NO synthetic fallback behind this port, by design — see
        `RoutingMarketDataProvider` and `MarketDataUnavailableError`. When an upstream
        provider is down, callers get an error and say so; they never get invented prices.

        `yfinance`/CoinGecko symbol overrides come from the prebuilt instrument
        universe's LIVE `coingecko_id_overrides()`/`yfinance_symbol_overrides()`
        dicts (CRITICAL fix, post-hoc adversarial review) — NOT a one-time
        snapshot comprehension over `all_rows()`. The previous snapshot approach
        meant a coin registered via `POST /instruments` after this provider was
        first built would never resolve a live price until process restart,
        because `CoinGeckoMarketDataProvider` holds `self._overrides` as a
        reference and the snapshot dict was never updated. Passing the SAME
        dict objects the universe mutates in `add_row()` makes every subsequent
        registration visible immediately, with no rebuild.
        """
        if self._market_data_provider is None:
            self.get_instrument_universe()  # raises if the universe wasn't built yet
            assert self._instrument_universe is not None
            coingecko_overrides = self._instrument_universe.coingecko_id_overrides()
            yfinance_overrides = self._instrument_universe.yfinance_symbol_overrides()
            self._market_data_provider = RoutingMarketDataProvider(
                yfinance_provider=YFinanceMarketDataProvider(symbol_overrides=yfinance_overrides),
                coingecko_provider=CoinGeckoMarketDataProvider(
                    base_url=self._settings.coingecko_base_url,
                    coingecko_id_overrides=coingecko_overrides,
                    cache_ttl_seconds=self._settings.coingecko_cache_ttl_seconds,
                    key_ring=self.get_coingecko_key_ring(),
                    cooldown_seconds=self._settings.coingecko_cooldown_seconds,
                    max_history_days=self._settings.coingecko_max_history_days,
                    http_client=self.get_http_client(),
                ),
            )
        return self._market_data_provider

    def get_instrument_metadata_provider(self) -> InstrumentMetadataProvider:
        """Return the cached CoinGecko `/coins/markets` batch metadata adapter.

        Backs `GET /instruments/enriched`'s additive `market_cap`/`volume_24h`/
        `change_7d_pct` fields (instrument-enrichment spec). Resolves symbol ->
        CoinGecko id from the prebuilt instrument universe's LIVE
        `coingecko_id_overrides()` dict — the SAME source
        `get_market_data_provider` uses for its own CoinGecko id resolution — so a
        coin registered via `POST /instruments` after this provider was first
        built still resolves without a container rebuild.
        """
        if self._instrument_metadata_provider is None:
            self.get_instrument_universe()  # raises if the universe wasn't built yet
            assert self._instrument_universe is not None
            self._instrument_metadata_provider = CoinGeckoInstrumentMetadataProvider(
                base_url=self._settings.coingecko_base_url,
                coingecko_id_overrides=self._instrument_universe.coingecko_id_overrides(),
                key_ring=self.get_coingecko_key_ring(),
                cooldown_seconds=self._settings.coingecko_cooldown_seconds,
                http_client=self.get_http_client(),
            )
        return self._instrument_metadata_provider

    def get_chart_config(self) -> ChartConfig:
        """Return the cached ChartConfig built from Settings (single source for chart limits)."""
        if self._chart_config is None:
            self._chart_config = ChartConfig(
                default_timeframe=self._settings.chart_default_timeframe,
                max_points=self._settings.chart_max_points,
                available_timeframes=list(self._settings.chart_available_timeframes),
                timeframe_days=dict(self._settings.chart_timeframe_days),
            )
        return self._chart_config

    def get_build_price_chart_use_case(self) -> BuildPriceChart:
        """Return the cached BuildPriceChart use case (shared by the chart tool + endpoint)."""
        if self._build_price_chart_use_case is None:
            self._build_price_chart_use_case = BuildPriceChart(
                market_data_provider=self.get_market_data_provider(),
                instrument_universe=self.get_instrument_universe(),
                chart_config=self.get_chart_config(),
            )
        return self._build_price_chart_use_case

    def get_build_comparison_chart_use_case(self) -> BuildComparisonChart:
        """Return the cached BuildComparisonChart use case."""
        if self._build_comparison_chart_use_case is None:
            self._build_comparison_chart_use_case = BuildComparisonChart(
                market_data_provider=self.get_market_data_provider(),
                instrument_universe=self.get_instrument_universe(),
                chart_config=self.get_chart_config(),
            )
        return self._build_comparison_chart_use_case

    def get_build_drawdown_chart_use_case(self) -> BuildDrawdownChart:
        """Return the cached BuildDrawdownChart use case."""
        if self._build_drawdown_chart_use_case is None:
            self._build_drawdown_chart_use_case = BuildDrawdownChart(
                market_data_provider=self.get_market_data_provider(),
                instrument_universe=self.get_instrument_universe(),
                chart_config=self.get_chart_config(),
            )
        return self._build_drawdown_chart_use_case

    def get_build_distribution_chart_use_case(self) -> BuildDistributionChart:
        """Return the cached BuildDistributionChart use case."""
        if self._build_distribution_chart_use_case is None:
            self._build_distribution_chart_use_case = BuildDistributionChart(
                market_data_provider=self.get_market_data_provider(),
                instrument_universe=self.get_instrument_universe(),
                chart_config=self.get_chart_config(),
            )
        return self._build_distribution_chart_use_case

    def get_build_macro_chart_use_case(self) -> BuildMacroChart:
        """Return the cached BuildMacroChart use case."""
        if self._build_macro_chart_use_case is None:
            self._build_macro_chart_use_case = BuildMacroChart(
                macro_data_provider=self.get_macro_data_provider(),
                chart_config=self.get_chart_config(),
            )
        return self._build_macro_chart_use_case

    def get_build_sentiment_gauge_use_case(self) -> BuildSentimentGauge:
        """Return the cached BuildSentimentGauge use case."""
        if self._build_sentiment_gauge_use_case is None:
            self._build_sentiment_gauge_use_case = BuildSentimentGauge(
                fear_greed_provider=self.get_fear_greed_provider(),
                chart_config=self.get_chart_config(),
            )
        return self._build_sentiment_gauge_use_case

    def get_render_chart_use_case(self) -> RenderChart:
        """Return the cached RenderChart dispatcher (timeframe-toggle endpoint)."""
        if self._render_chart_use_case is None:
            self._render_chart_use_case = RenderChart(
                build_price_chart=self.get_build_price_chart_use_case(),
                build_comparison_chart=self.get_build_comparison_chart_use_case(),
                build_drawdown_chart=self.get_build_drawdown_chart_use_case(),
                build_distribution_chart=self.get_build_distribution_chart_use_case(),
                build_macro_chart=self.get_build_macro_chart_use_case(),
                build_sentiment_gauge=self.get_build_sentiment_gauge_use_case(),
            )
        return self._render_chart_use_case

    def get_generate_consequence_chain_use_case(self) -> GenerateConsequenceChain:
        """Return the cached Consequence Chain Analyst use case (issue #8).

        Shared between the `consequence` chat specialist's tool
        (`_get_chat_graph` below, via `build_consequence_tools`) and
        `POST /api/v1/consequence-chains/generate`
        (`api/v1/dependencies/get_generate_consequence_chain_use_case.py`) — both surfaces
        call the exact same `GenerateConsequenceChain.execute(subject)`. Only depends on
        `LLMProvider`, so — unlike `GenerateSignal`, which the signals router builds
        per-request from several ports — caching one instance here is safe and cheap.
        """
        if self._generate_consequence_chain_use_case is None:
            self._generate_consequence_chain_use_case = GenerateConsequenceChain(
                # Reasoning tier (#28): a causal X->Y->Z chain with per-edge mechanisms is
                # multi-step reasoning, not extraction.
                llm_provider=self.get_reasoning_llm_provider()
            )
        return self._generate_consequence_chain_use_case

    def get_generate_conversation_title_use_case(self) -> GenerateConversationTitle:
        """Return the cached conversation-title generator (issue #53 backend half).

        Reuses the `LLMProvider` port and injects the short `MIDAS_VOICE_HINT` (not the full
        `MIDAS_PERSONA`) as the voice preamble: a 3-6 word title needs only the tone, not the
        whole grounding/scope/recommendation rulebook, so the compact hint keeps the voice while
        trimming the prompt. `application/` still stays free of any infrastructure persona import.
        Backs `POST /api/v1/chat/title`.
        """
        if self._generate_conversation_title_use_case is None:
            self._generate_conversation_title_use_case = GenerateConversationTitle(
                # Fast tier (#28): summarizing a turn into a few words.
                llm_provider=self.get_fast_llm_provider(),
                voice_preamble=MIDAS_VOICE_HINT,
            )
        return self._generate_conversation_title_use_case

    def get_macro_data_provider(self) -> MacroDataProvider:
        """Return the routing MacroDataProvider (FRED rates/CPI + yfinance VIX). No fixtures.

        `FRED_API_KEY` gates live rates/CPI (VIX needs no key). A live failure — including a
        missing key — now raises `MacroDataUnavailableError` instead of quietly serving
        invented rates and CPI prints. See `infrastructure/macro/routing_macro_data_provider.py`.
        """
        if self._macro_data_provider is None:
            indicator_series_ids = {
                MacroIndicator.RATES: self._settings.fred_rates_series_id,
                MacroIndicator.CPI: self._settings.fred_cpi_series_id,
                MacroIndicator.GOLD: self._settings.fred_gold_series_id,
                MacroIndicator.OIL: self._settings.fred_oil_series_id,
                MacroIndicator.TREASURY_10Y: self._settings.fred_treasury_10y_series_id,
            }
            live_provider = FredMacroDataProvider(
                api_key=self._settings.fred_api_key,
                base_url=self._settings.fred_base_url,
                rates_series_id=self._settings.fred_rates_series_id,
                cpi_series_id=self._settings.fred_cpi_series_id,
                vix_symbol=self._settings.vix_symbol,
                low_threshold=self._settings.vix_low_threshold,
                elevated_threshold=self._settings.vix_elevated_threshold,
                high_threshold=self._settings.vix_high_threshold,
                indicator_series_ids=indicator_series_ids,
                timeout_seconds=self._settings.fred_timeout_seconds,
                http_client=self.get_http_client(),
            )
            self._macro_data_provider = RoutingMacroDataProvider(live_provider=live_provider)
        return self._macro_data_provider

    def get_interpret_macro_event_use_case(self) -> InterpretMacroEvent:
        """Return the cached Macro Analyst use case (issue #21).

        Shared between the `macro` chat specialist's tool (`_get_chat_graph` below, via
        `build_macro_tools`) and `POST /api/v1/macro/interpret`
        (`api/v1/dependencies/get_interpret_macro_event_use_case.py`) — both surfaces call
        the exact same `InterpretMacroEvent.execute(event_description, locale)`, grounded in
        the same `get_macro_data_provider()` instance every other macro-aware pipeline uses.
        """
        if self._interpret_macro_event_use_case is None:
            self._interpret_macro_event_use_case = InterpretMacroEvent(
                macro_data_provider=self.get_macro_data_provider(),
                # Reasoning tier (#28). Borderline — it's one structured call over pre-fetched
                # numbers — but it reasons causally about direction/magnitude PER ASSET CLASS,
                # so it defaults up. Cheap to move down to fast if cost matters.
                llm_provider=self.get_reasoning_llm_provider(),
            )
        return self._interpret_macro_event_use_case

    def get_event_analyzer(self) -> EventAnalyzerPort:
        """Return the cached Gemini-based event analyzer for the Sentinel pipeline.

        Falls back to a zero-signal result when `GEMINI_API_KEY` is unset —
        same graceful-degradation pattern as `get_agent_memory`'s Redis fallback.
        """
        if self._event_analyzer is None:
            self._event_analyzer = GeminiEventAnalyzer(
                api_key=self._settings.gemini_api_key,
                model=self._settings.gemini_model,
                # The Sentinel path has no request to read a locale from — a scheduled scan
                # broadcasts to every linked user at once — so the configured default is what a
                # market-wide alert is written in.
                locale=self._settings.default_locale,
            )
        return self._event_analyzer

    def get_event_repository(self) -> EventRepositoryPort:
        """Return Supabase-backed events, with process-local storage for unconfigured dev.

        This used to return `MemoryEventRepository` UNCONDITIONALLY — a plain `list[]` that
        was the port's only implementation, with no environment gate. Every Sentinel scan
        wrote its Gemini-enriched events into one worker's RAM, so a restart erased them and
        a second worker never saw them. That broke a user-visible flow, not just "state":
        Telegram alert buttons carry an event id in their callback data, and
        `EventCallbackHandler` resolves it through `get(...)` — so the buttons on a
        still-visible alert went permanently dead after any deploy.

        Now `SupabaseEventRepository` (migration 0021) is the real adapter, and the
        in-memory one is a DEVELOPMENT-ONLY convenience, gated exactly like
        `get_note_repository`: it engages only when Supabase isn't configured AND
        `app_env == "development"`. In any other environment a missing Supabase config
        surfaces as a real failure instead of silently discarding every event.
        """
        if self._event_repository is None:
            supabase_configured = bool(self._settings.supabase_url and self._settings.supabase_key)
            if self._settings.app_env == "development" and not supabase_configured:
                logging.getLogger(__name__).warning(
                    "Supabase events are not configured; using process-local development "
                    "storage. Enriched events will not survive a restart."
                )
                self._event_repository = MemoryEventRepository()
            else:
                self._event_repository = SupabaseEventRepository(
                    supabase_url=self._settings.supabase_url,
                    supabase_key=self._settings.supabase_key,
                    retry_max_attempts=self._settings.supabase_retry_max_attempts,
                    retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
                )
        return self._event_repository

    def get_event_news_provider(self) -> NewsProviderPort:
        """Return the cached news source feeding the Sentinel (Gemini) pipeline.

        `MarketNewsEventProvider`, bridging to the SAME live `get_news_provider()` the radar and
        every other pipeline already use (Marketaux/NewsAPI/Finnhub/RSS/SEC EDGAR, with a
        fixture fallback baked into `AggregatingNewsProvider` when nothing is configured).

        This used to be hardwired to `DemoNewsProvider` — 43 canned articles with `example.com`
        URLs — which was fine while the only consumer was a manual "prove the wiring works"
        button, but made no sense once a scheduled scan started broadcasting news to real users:
        it could only ever alert people about demo text. That provider has since been deleted
        outright rather than left exported, so it cannot be swapped back in by accident.
        """
        if self._event_news_provider is None:
            self._event_news_provider = MarketNewsEventProvider(
                news_provider=self.get_news_provider(),
                since_hours=self._settings.sentinel_news_since_hours,
                limit=self._settings.sentinel_news_fetch_limit,
            )
        return self._event_news_provider

    def get_process_incoming_event_use_case(self) -> ProcessIncomingEvent:
        """Return the cached Event Intelligence use case (Sentinel pipeline).

        Wires the Gemini analyzer and in-memory repository together.
        """
        if self._process_incoming_event_use_case is None:
            self._process_incoming_event_use_case = ProcessIncomingEvent(
                analyzer=self.get_event_analyzer(),
                repository=self.get_event_repository(),
            )
        return self._process_incoming_event_use_case

    def get_processed_event_tracker(self) -> ProcessedEventTracker:
        """Return the cached, process-wide `ProcessedEventTracker` singleton.

        Must be a singleton: its in-process "already analyzed" set is the only thing stopping
        the scheduled Sentinel scan from re-billing Gemini for, and re-broadcasting, the same
        headline on every tick (poll windows deliberately overlap).
        """
        if self._processed_event_tracker is None:
            self._processed_event_tracker = ProcessedEventTracker()
        return self._processed_event_tracker

    def get_broadcast_important_events_use_case(self) -> BroadcastImportantEvents:
        """Return the cached Sentinel scan use case (poll -> analyze -> gate -> broadcast).

        The automatic replacement for the manual "send a news analysis to Telegram" button. Runs
        on the scheduler (`sentinel-news-scan`); see `BroadcastImportantEvents` for why it gates
        on both Gemini's `should_notify` and a configurable importance floor, and why the number
        of alerts per run is capped.
        """
        if self._broadcast_important_events_use_case is None:
            self._broadcast_important_events_use_case = BroadcastImportantEvents(
                news_provider=self.get_event_news_provider(),
                process_incoming_event=self.get_process_incoming_event_use_case(),
                notification_channel=self.get_notification_channel(),
                processed_event_tracker=self.get_processed_event_tracker(),
                importance_threshold=self._settings.sentinel_importance_threshold,
                max_alerts_per_run=self._settings.sentinel_max_alerts_per_run,
                max_concurrency=self._settings.sentinel_max_concurrency,
            )
        return self._broadcast_important_events_use_case

    def get_event_callback_handler(self) -> EventCallbackHandler | None:
        """Return the cached handler for a tapped inline button on a broadcast news alert.

        `None` when `TELEGRAM_BOT_TOKEN` is unset — same `None`-gate every other Telegram
        feature uses: with no bot there is no message carrying buttons, so nothing can be
        tapped and there is nothing to answer.
        """
        if self._event_callback_handler is None:
            messenger = self.get_telegram_messenger()
            chat_handler = self.get_chat_message_handler()
            if messenger is None or chat_handler is None:
                return None
            self._event_callback_handler = EventCallbackHandler(
                event_repository=self.get_event_repository(),
                # Constructed inline, matching `_build_impact_command_handler` above — it's a
                # single-port wrapper over the analyzer, so there's nothing to cache.
                analyze_event_impact=AnalyzeEventImpact(analyzer=self.get_event_analyzer()),
                chat_message_handler=chat_handler,
                messenger=messenger,
            )
        return self._event_callback_handler

    def get_fear_greed_provider(self) -> FearGreedProvider:
        """Return the routing FearGreedProvider (alternative.me). No fixture fallback.

        No API key required for the live adapter. Any failure (network error, malformed
        payload, unrecognized classification label) now raises `FearGreedUnavailableError`
        rather than inventing a market mood — see
        `infrastructure/sentiment/routing_fear_greed_provider.py`.
        """
        if self._fear_greed_provider is None:
            live_provider = AlternativeMeFearGreedProvider(
                base_url=self._settings.alternative_me_base_url,
                timeout_seconds=self._settings.alternative_me_timeout_seconds,
                http_client=self.get_http_client(),
            )
            self._fear_greed_provider = RoutingFearGreedProvider(live_provider=live_provider)
        return self._fear_greed_provider

    def get_analyze_sentiment_use_case(self) -> AnalyzeSentiment:
        """Return the cached Sentiment Analyst use case (issue #21).

        Shared between the `sentiment` chat specialist's tool (`_get_chat_graph` below,
        via `build_sentiment_tools`) and `POST /api/v1/sentiment/{symbol}/analyze`
        (`api/v1/dependencies/get_analyze_sentiment_use_case.py`) — both surfaces call the
        exact same `AnalyzeSentiment.execute(instrument_symbol)`, grounded in the same
        `get_news_provider()` (which now includes SEC EDGAR filings, issue #21) and
        `get_fear_greed_provider()` instances every other pipeline uses.
        """
        if self._analyze_sentiment_use_case is None:
            self._analyze_sentiment_use_case = AnalyzeSentiment(
                news_provider=self.get_news_provider(),
                fear_greed_provider=self.get_fear_greed_provider(),
                instrument_universe=self.get_instrument_universe(),
                # Fast tier (#28): bucketing coverage into a -1..1 tone score is a
                # classification call, not analysis — `mini` is already right for it.
                llm_provider=self.get_fast_llm_provider(),
                # Persisted + freshness-cached since #29 (it used to be recomputed every call
                # and thrown away).
                sentiment_repository=self.get_sentiment_repository(),
                freshness_policy=self.get_freshness_policy(),
                retention_keep=self._settings.analysis_retention_keep,
                bullish_threshold=self._settings.sentiment_bullish_threshold,
                bearish_threshold=self._settings.sentiment_bearish_threshold,
            )
        return self._analyze_sentiment_use_case

    def get_fundamentals_provider(self) -> FundamentalsProvider:
        """Return the routing FundamentalsProvider (yfinance). No fixture fallback.

        A live `yfinance` failure now raises `FundamentalsUnavailableError` rather than
        degrading to an invented P/E or earnings date — see
        `infrastructure/fundamentals/routing_fundamentals_provider.py`.
        """
        if self._fundamentals_provider is None:
            risk_window_days = self._settings.upcoming_earnings_risk_window_days
            self._fundamentals_provider = RoutingFundamentalsProvider(
                live_provider=YFinanceFundamentalsProvider(risk_window_days=risk_window_days)
            )
        return self._fundamentals_provider

    def get_preset_scenario_rows(self) -> list[dict[str, Any]]:
        """Return the curated preset scenario rows (raw JSON, bilingual copy included).

        Backs `GET /api/v1/scenarios/presets` (a preset picker listing) — the normalized,
        English-only, pipeline-ready `ScenarioSpec` shape those rows map onto lives behind
        `get_scenario_simulation_runner()`'s Intake step instead, see
        `build_scenario_spec_from_preset.py`. `load_preset_scenarios_seed` is itself
        `@lru_cache`d, so no separate instance-level caching is needed here.
        """
        return load_preset_scenarios_seed(self._settings.preset_scenarios_seed_path)

    def get_scenario_repository(self) -> ScenarioRepository:
        if self._scenario_repository is None:
            self._scenario_repository = SupabaseScenarioRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._scenario_repository

    def get_scenario_simulation_runner(self) -> ScenarioSimulationRunner:
        """Return the cached Scenario Simulation graph runner (issue #12).

        Builds every step's use case from existing ports/use cases only — `GatherScenarioContext`
        reuses `FindHistoricalAnalogs` (issue #15) exactly like `signals.py`'s router builds it
        per-request, and `build_scenario_graph` reuses `get_generate_consequence_chain_use_case()`
        directly (issue #8) rather than constructing a second `GenerateConsequenceChain`. Shared
        between `POST /api/v1/scenarios/generate` and the `run_scenario_simulation` chat tool
        (`_get_chat_graph` below) — both call the exact same compiled graph.
        """
        if self._scenario_simulation_runner is None:
            preset_rows = load_preset_scenarios_seed(self._settings.preset_scenarios_seed_path)
            normalize_intake = NormalizeScenarioIntake(
                # Fast tier (#28): free text -> a `ScenarioSpec`. Extraction, not reasoning.
                llm_provider=self.get_fast_llm_provider(),
                instrument_universe=self.get_instrument_universe(),
                preset_rows=preset_rows,
            )
            gather_context = GatherScenarioContext(
                market_data_provider=self.get_market_data_provider(),
                instrument_universe=self.get_instrument_universe(),
                news_provider=self.get_news_provider(),
                macro_data_provider=self.get_macro_data_provider(),
                find_historical_analogs=FindHistoricalAnalogs(
                    embedding_provider=self.get_embedding_provider(),
                    vector_store=self.get_vector_store(),
                    top_k=self._settings.historical_analogs_top_k,
                ),
            )
            compute_quantification = ComputeScenarioQuantification(
                market_data_provider=self.get_market_data_provider(),
                instrument_universe=self.get_instrument_universe(),
            )
            synthesize_result = SynthesizeScenarioResult(
                # Reasoning tier (#28): spec + causal chain + evidence -> a quantified
                # per-asset-class impact map. The heaviest call in the scenario graph.
                llm_provider=self.get_reasoning_llm_provider(),
                instrument_universe=self.get_instrument_universe(),
                max_synthesis_attempts=self._settings.scenario_synthesis_max_attempts,
            )
            generate_contributions = GenerateScenarioAgentContributions(
                # Reasoning tier (#28): six independent grounded specialists produce
                # judgments that the final synthesis must reconcile.
                llm_provider=self.get_reasoning_llm_provider(),
                midas_persona=MIDAS_PERSONA,
                specialist_personas={
                    ScenarioAgentId.ANALYST: ANALYST_PERSONA,
                    ScenarioAgentId.QUANT: QUANT_PERSONA,
                    ScenarioAgentId.MACRO: MACRO_PERSONA,
                    ScenarioAgentId.SENTIMENT: SENTIMENT_PERSONA,
                    ScenarioAgentId.CONSEQUENCE: CONSEQUENCE_PERSONA,
                    ScenarioAgentId.ADVISOR: ADVISOR_PERSONA,
                },
                max_concurrency=self._settings.scenario_agent_panel_max_concurrency,
                max_attempts=self._settings.scenario_agent_panel_max_attempts,
            )
            graph = build_scenario_graph(
                normalize_scenario_intake=normalize_intake,
                gather_scenario_context=gather_context,
                generate_consequence_chain=self.get_generate_consequence_chain_use_case(),
                compute_scenario_quantification=compute_quantification,
                generate_agent_contributions=generate_contributions,
                synthesize_scenario_result=synthesize_result,
                scenario_repository=self.get_scenario_repository(),
            )
            self._scenario_simulation_runner = ScenarioSimulationRunner(
                graph=graph,
                # Freshness gate + retention for PRESET runs (#29); free-form runs have no
                # stable cache key and always execute the graph.
                scenario_repository=self.get_scenario_repository(),
                freshness_policy=self.get_freshness_policy(),
                retention_keep=self._settings.analysis_retention_keep,
            )
        return self._scenario_simulation_runner

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

    def get_generate_signal_use_case(self) -> GenerateSignal:
        """Build the Analyst `GenerateSignal` pipeline from its ports.

        NOT cached: `GenerateSignal` composes several ports (news/market/universe/signal
        repo/LLM + the analog RAG pair) — the collaborators it depends on are themselves cached
        singletons, so the only per-call cost is wiring a thin orchestrator.

        THE single construction site (issue #29). The signals router, the news router's
        analyze-pending / force-analyze endpoints, the scheduler's ticks, and the realtime tool
        all resolve the pipeline from here, so the freshness gate, the retention count, and the
        retry policy can't drift between "the endpoint" and "the scheduled job" — which is
        exactly what was starting to happen while several call sites each hand-assembled their
        own `GenerateSignal` with a different subset of the settings.
        """
        return GenerateSignal(
            news_provider=self.get_news_provider(),
            market_data_provider=self.get_market_data_provider(),
            instrument_universe=self.get_instrument_universe(),
            signal_repository=self.get_signal_repository(),
            # Reasoning tier (#28): news + price + analogs -> a thesis with drivers and risks.
            # The flagship analytical call in the product.
            llm_provider=self.get_reasoning_llm_provider(),
            find_historical_analogs=FindHistoricalAnalogs(
                embedding_provider=self.get_embedding_provider(),
                vector_store=self.get_vector_store(),
                top_k=self._settings.historical_analogs_top_k,
            ),
            index_signal_analog=IndexSignalAnalog(
                embedding_provider=self.get_embedding_provider(),
                vector_store=self.get_vector_store(),
            ),
            min_distinct_sources=self._settings.min_distinct_news_sources,
            freshness_policy=self.get_freshness_policy(),
            retention_keep=self._settings.analysis_retention_keep,
            retry_max_attempts=self._settings.signal_classification_retry_max_attempts,
            retry_backoff_base_seconds=(
                self._settings.signal_classification_retry_backoff_base_seconds
            ),
        )

    def get_analyze_pending_news_use_case(self) -> AnalyzePendingNews:
        """Build the pending-news batch analysis pipeline (issue #2).

        NOT cached, same rationale as `get_generate_signal_use_case`. Shared by
        `POST /api/v1/news/analyze-pending` and the scheduler's `analyze-pending-news` tick, so
        the gate settings can never differ between the manual trigger and the background one.
        """
        return AnalyzePendingNews(
            news_item_repository=self.get_news_item_repository(),
            instrument_universe=self.get_instrument_universe(),
            # Reuses the one `GenerateSignal` construction site (which picks the reasoning tier,
            # #28) rather than re-assembling the pipeline from its ports.
            generate_signal=self.get_generate_signal_use_case(),
            prefilter_policy=self.get_news_prefilter_policy(),
            max_concurrency=self._settings.news_analysis_max_concurrency,
            batch_limit=self._settings.news_analysis_batch_limit,
        )

    def get_score_news_sentiment_use_case(self) -> ScoreNewsSentiment:
        """Build the per-article sentiment scoring pass.

        NOT cached, same rationale as `get_analyze_pending_news_use_case`. Uses the reasoning
        tier like every other classification call site (#28) — scoring an article's tone is the
        same kind of judgment as classifying its impact, and a cheaper tier is exactly where a
        rater starts inventing directions for procedural filings.
        """
        return ScoreNewsSentiment(
            news_item_repository=self.get_news_item_repository(),
            llm_provider=self.get_reasoning_llm_provider(),
            batch_size=self._settings.news_sentiment_batch_limit,
            chunk_size=self._settings.news_sentiment_chunk_size,
        )

    def get_force_analyze_news_item_use_case(self) -> ForceAnalyzeNewsItem:
        """Build the manual "Analizar ahora" per-item pipeline (issue #27).

        Wraps the SAME `GenerateSignal` every other surface uses — and calls it with
        `force=True`, so the button genuinely re-analyzes instead of being handed the cached
        signal the freshness gate would otherwise return (issue #29).
        """
        return ForceAnalyzeNewsItem(
            news_item_repository=self.get_news_item_repository(),
            generate_signal=self.get_generate_signal_use_case(),
        )

    def get_refresh_tracked_analysis_use_case(self) -> RefreshTrackedAnalysis:
        """Return the cached background-refresh use case (issue #29).

        Cached (unlike the pipelines above) because it holds no per-request state and is
        resolved on every scheduler tick. Shared by that tick, by
        `POST /api/v1/analysis/refresh`, and by the watchlist-add seed — one code path, so a
        manual refresh and a scheduled one behave identically (the same "on-demand endpoint
        runs the exact scheduled-job use case" pattern `POST /api/v1/watchdog/scan` set).
        """
        if self._refresh_tracked_analysis_use_case is None:
            self._refresh_tracked_analysis_use_case = RefreshTrackedAnalysis(
                watchlist_repository=self.get_watchlist_repository(),
                generate_signal=self.get_generate_signal_use_case(),
                analyze_sentiment=self.get_analyze_sentiment_use_case(),
                # The accessor, not the universe: see `RefreshTrackedAnalysis.__init__`. Calling
                # it here would make `POST /watchlists/{id}/items` — which resolves this use
                # case via `Depends` purely to seed ONE symbol — fail whenever the universe
                # isn't built, even though the seed path never reads it.
                instrument_universe=self.get_instrument_universe,
                locales=self._settings.analysis_refresh_locales,
                max_concurrency=self._settings.analysis_refresh_concurrency,
                cover_universe=self._settings.analysis_refresh_cover_universe,
                max_symbols=self._settings.analysis_refresh_max_symbols,
            )
        return self._refresh_tracked_analysis_use_case

    def get_realtime_session_provider(self) -> RealtimeSessionProvider | None:
        """Return the cached `RealtimeSessionProvider`, or `None` when Realtime is off.

        Gated like `get_tts_provider`/`get_notification_channel`: returns `None` (not an
        exception) so the `/chat/realtime/*` endpoints can degrade to 503 and the
        frontend can hide the Talk button. Enabled only when `OPENAI_REALTIME_ENABLED`
        is set AND a key is available. Hackathon-friction fallback: the dedicated
        `openai_realtime_api_key` is preferred, but an unset one falls back to
        `openai_api_key` so a single key can drive both plain chat and voice while the
        billed Realtime key stays optional to configure. Only the built adapter is
        cached (not the `None`), matching `get_telegram_messenger`'s pattern — gating is
        cheap and deterministic from `Settings`.
        """
        if self._realtime_session_provider is not None:
            return self._realtime_session_provider
        if not self._settings.openai_realtime_enabled:
            return None
        api_key = self._settings.openai_realtime_api_key or self._settings.openai_api_key
        if not api_key:
            return None
        self._realtime_session_provider = OpenAIRealtimeSessionProvider(api_key=api_key)
        return self._realtime_session_provider

    def _get_router_chat_model(self) -> BaseChatModel:
        """Build/cache the FAST chat model backing the supervisor's routing node (issue #28).

        Picking 1 of 6 specialists is a pure structured-output classification — the cheapest
        model in the config is already correct at it, and it runs on every single chat turn.

        Used ONLY by the chat/SSE agent graph below. The Analyst signal / Advisor briefing
        pipelines do NOT use this — they depend on the `LLMProvider` port
        (`get_fast_llm_provider()` / `get_reasoning_llm_provider()`) instead, per the hexagonal
        rule that `application/` never imports a vendor/framework package directly (see
        `application/signals/use_cases/generate_signal.py`'s docstring). Kept private for that
        reason: nothing outside `_get_chat_graph` should reach for a raw `BaseChatModel`.
        """
        if self._router_chat_model is None:
            self._router_chat_model = build_chat_model(
                self._settings,
                self._settings.openai_model,
                temperature=self._settings.router_temperature,
            )
        return self._router_chat_model

    def _get_specialist_chat_model(self) -> BaseChatModel:
        """Build/cache the REASONING chat model backing all 6 specialist nodes (issue #28).

        The specialists run a multi-turn tool-calling loop over real analytical work (the heavy
        math lives in the injected tools, but the interpretation doesn't), so they're the half
        of the graph that actually benefits from a stronger model. Same privacy rationale as
        `_get_router_chat_model`.
        """
        if self._specialist_chat_model is None:
            self._specialist_chat_model = build_chat_model(
                self._settings, self._settings.reasoning_model
            )
        return self._specialist_chat_model

    def _get_chat_graph(self) -> Any:
        if self._chat_graph is None:
            checkpointer = self.get_agent_memory().get_checkpointer()
            # Signal + news grounding: see `build_advisor_grounding_tools`'s docstring for
            # why briefing/watchlist grounding tools were removed (unauthenticated chat
            # route + no per-user ownership check would leak cross-tenant data), and why
            # `get_news` is safe to add (market-wide, not per-user — a news question that the
            # router sends to the catch-all advisor now grounds instead of dead-ending). The
            # Scenario Simulation tool is safe on top for the same reason — `ScenarioResult`s
            # aren't per-user data either (see `ScenarioRepository`'s docstring) — so it's
            # kept in its own builder (`build_scenario_tools`, not "grounding") and
            # concatenated here rather than folded into `build_advisor_grounding_tools`.
            advisor_tools = (
                build_advisor_grounding_tools(
                    signal_repository=self.get_signal_repository(),
                    news_provider=self.get_news_provider(),
                )
                + build_scenario_tools(
                    scenario_simulation_runner=self.get_scenario_simulation_runner(),
                    default_locale=self._settings.default_locale,
                )
                + build_event_intelligence_tools(
                    event_repository=self.get_event_repository(),
                )
            )
            # Every `default_locale` passed to a tool builder below is now only a FALLBACK, not
            # the locale the tool runs in: the locale-aware tools read the turn's locale from
            # their injected `RunnableConfig`, which `LangGraphAgentRunner.stream` populates per
            # request (see `infrastructure/agents/tools/resolve_tool_locale.py`). It still
            # applies wherever there's no per-turn locale to read — the Telegram and scheduled
            # paths, and direct calls outside a graph run.
            consequence_tools = build_consequence_tools(
                use_case=self.get_generate_consequence_chain_use_case(),
                default_locale=self._settings.default_locale,
            )
            # `quant` grounding tools: safe for the unauthenticated chat route (public
            # market data, not per-user) — see `build_quant_grounding_tools`'s docstring.
            quant_tools = build_quant_grounding_tools(
                compute_market_stats=ComputeMarketStats(
                    market_data_provider=self.get_market_data_provider(),
                    instrument_universe=self.get_instrument_universe(),
                ),
                compute_event_study=ComputeEventStudy(
                    market_data_provider=self.get_market_data_provider(),
                    instrument_universe=self.get_instrument_universe(),
                ),
            )
            # `macro`/`sentiment` tools (issue #21): both public, non-per-user data — same
            # "safe for the unauthenticated chat route" rationale as `quant_tools` above.
            macro_tools = build_macro_tools(
                use_case=self.get_interpret_macro_event_use_case(),
                default_locale=self._settings.default_locale,
            )
            sentiment_tools = build_sentiment_tools(
                use_case=self.get_analyze_sentiment_use_case(),
                default_locale=self._settings.default_locale,
            )
            analyst_tools = build_analyst_grounding_tools(
                news_provider=self.get_news_provider(),
                generate_signal=self.get_generate_signal_use_case(),
                default_locale=self._settings.default_locale,
            )
            # Whole-universe ranking (`get_market_movers`): bound to BOTH the advisor (the
            # catch-all where "what moved today?" lands) and the analyst — see
            # `build_market_overview_tools`'s docstring. Public market data only, so it
            # passes the same chat-route safety test as `quant_tools`.
            market_overview_tools = build_market_overview_tools(
                list_enriched_instruments=self.get_list_enriched_instruments_use_case(),
                default_locale=self._settings.default_locale,
            )
            advisor_tools = advisor_tools + market_overview_tools
            analyst_tools = analyst_tools + market_overview_tools
            # Tools audit (2026-07-16). `get_fundamentals` / `get_macro_state` are public
            # market data — same chat-route safety test as `quant_tools`. `get_watchlist`
            # is per-user: it reads the acting user id from the run config (the verified
            # JWT id `LangGraphAgentRunner.stream` publishes), NEVER from model arguments —
            # see `resolve_tool_user_id`. That ownership pattern is what re-admits per-user
            # grounding after the pre-auth removal `build_advisor_grounding_tools` records.
            fundamentals_tool = build_get_fundamentals_tool(self.get_fundamentals_provider())
            macro_state_tool = build_get_macro_state_tool(self.get_macro_data_provider())
            watchlist_tool = build_get_watchlist_tool(
                watchlist_repository=self.get_watchlist_repository(),
                compute_market_stats=ComputeMarketStats(
                    market_data_provider=self.get_market_data_provider(),
                    instrument_universe=self.get_instrument_universe(),
                ),
            )
            advisor_tools = advisor_tools + [watchlist_tool, fundamentals_tool, macro_state_tool]
            analyst_tools = analyst_tools + [fundamentals_tool]
            macro_tools = macro_tools + [macro_state_tool]
            if self._settings.charts_enabled:
                config = self.get_chart_config()
                quant_tools = quant_tools + [
                    build_render_price_chart_tool(
                        build_price_chart=self.get_build_price_chart_use_case(),
                        chart_config=config,
                    ),
                    build_render_comparison_chart_tool(
                        build_comparison_chart=self.get_build_comparison_chart_use_case(),
                        chart_config=config,
                    ),
                    build_render_drawdown_chart_tool(
                        build_drawdown_chart=self.get_build_drawdown_chart_use_case(),
                        chart_config=config,
                    ),
                    build_render_distribution_chart_tool(
                        build_distribution_chart=self.get_build_distribution_chart_use_case(),
                        chart_config=config,
                    ),
                ]
                analyst_tools = analyst_tools + [
                    build_render_price_chart_tool(
                        build_price_chart=self.get_build_price_chart_use_case(),
                        chart_config=config,
                    ),
                    # The analyst is the specialist that produces comparison/impact analysis
                    # (generate_signal), so it also needs the visuals that explain a comparison —
                    # otherwise a "compara la rentabilidad de X vs Y" answer is text-only because
                    # the only specialist with render_comparison_chart never sees the turn.
                    build_render_comparison_chart_tool(
                        build_comparison_chart=self.get_build_comparison_chart_use_case(),
                        chart_config=config,
                    ),
                    build_render_drawdown_chart_tool(
                        build_drawdown_chart=self.get_build_drawdown_chart_use_case(),
                        chart_config=config,
                    ),
                ]
                advisor_tools = advisor_tools + [
                    build_render_comparison_chart_tool(
                        build_comparison_chart=self.get_build_comparison_chart_use_case(),
                        chart_config=config,
                    )
                ]
                consequence_tools = consequence_tools + [
                    build_render_price_chart_tool(
                        build_price_chart=self.get_build_price_chart_use_case(),
                        chart_config=config,
                    )
                ]
                macro_tools = macro_tools + [
                    build_render_macro_chart_tool(
                        build_macro_chart=self.get_build_macro_chart_use_case(),
                        chart_config=config,
                    )
                ]
                sentiment_tools = sentiment_tools + [
                    build_render_sentiment_gauge_tool(
                        build_sentiment_gauge=self.get_build_sentiment_gauge_use_case(),
                    ),
                    build_render_distribution_chart_tool(
                        build_distribution_chart=self.get_build_distribution_chart_use_case(),
                        chart_config=config,
                    ),
                ]
            self._chat_graph = build_supervisor_graph(
                self._get_router_chat_model(),
                self._get_specialist_chat_model(),
                checkpointer,
                self._settings.router_history_max_messages,
                self._settings.chat_history_max_messages,
                advisor_tools=advisor_tools,
                analyst_tools=analyst_tools,
                consequence_tools=consequence_tools,
                macro_tools=macro_tools,
                quant_tools=quant_tools,
                sentiment_tools=sentiment_tools,
                # Fast tier for the cheap scope terminals (smalltalk / out_of_scope).
                scope_model=self._get_router_chat_model(),
            )
        return self._chat_graph


@lru_cache
def get_container() -> Container:
    """Return a process-wide cached Container, built from the cached Settings."""
    return Container(settings=get_settings())
