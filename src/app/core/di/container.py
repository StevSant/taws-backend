import logging
from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
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
from app.application.event_intelligence.use_cases import AnalyzeEventImpact, ProcessIncomingEvent
from app.application.instruments.use_cases import RegisterInstrument, SearchCoins
from app.application.macro.use_cases import InterpretMacroEvent
from app.application.quant.use_cases import ComputeEventStudy, ComputeMarketStats
from app.application.scenario.use_cases import (
    ComputeScenarioQuantification,
    GatherScenarioContext,
    NormalizeScenarioIntake,
    SynthesizeScenarioResult,
)
from app.application.sentiment.use_cases import AnalyzeSentiment
from app.application.signals.use_cases import GenerateSignal
from app.application.telegram.use_cases import LinkTelegramAccount
from app.application.watchdog import AlertedSignalTracker
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
from app.domain.market.entities import MacroIndicator
from app.domain.market.ports import (
    CoinGeckoSearchProvider,
    FundamentalsProvider,
    InstrumentCatalogRepository,
    InstrumentUniverse,
    MacroDataProvider,
    MarketDataProvider,
    NewsItemRepository,
    NewsProvider,
)
from app.domain.notes.ports import NoteRepository
from app.domain.notification.ports import EmailSender, NotificationChannel
from app.domain.scenario.ports import ScenarioRepository
from app.domain.sentiment.ports import FearGreedProvider
from app.domain.signals.ports import SignalRepository
from app.domain.telegram.ports import (
    BotRegistrationPort,
    TelegramLinkRepository,
    TelegramLinkTokenRepository,
    TelegramMessenger,
    UserBotRepository,
)
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.agents import LangGraphAgentRunner, build_supervisor_graph
from app.infrastructure.agents.personas import MIDAS_PERSONA
from app.infrastructure.agents.scenario import ScenarioSimulationRunner, build_scenario_graph
from app.infrastructure.agents.tools import (
    build_advisor_grounding_tools,
    build_analyst_grounding_tools,
    build_consequence_tools,
    build_event_intelligence_tools,
    build_macro_tools,
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
from app.infrastructure.event_intelligence.providers import DemoNewsProvider
from app.infrastructure.event_intelligence.repositories import MemoryEventRepository
from app.infrastructure.fundamentals import (
    FixtureFundamentalsProvider,
    RoutingFundamentalsProvider,
    YFinanceFundamentalsProvider,
)
from app.infrastructure.llm import OpenAIProvider, build_chat_model
from app.infrastructure.macro import (
    FixtureMacroDataProvider,
    FredMacroDataProvider,
    RoutingMacroDataProvider,
)
from app.infrastructure.marketdata import (
    CoinGeckoCoinSearchProvider,
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
    SecEdgarNewsProvider,
)
from app.infrastructure.notification import (
    LoggingEmailSender,
    LoggingNotificationChannel,
    TelegramNotificationChannel,
)
from app.infrastructure.persistence import (
    SupabaseBriefingRepository,
    SupabaseConversationRepository,
    SupabaseInstrumentCatalogRepository,
    SupabaseNewsItemRepository,
    SupabaseNoteRepository,
    SupabaseScenarioRepository,
    SupabaseSignalRepository,
    SupabaseTelegramLinkRepository,
    SupabaseTelegramLinkTokenRepository,
    SupabaseUserBotRepository,
    SupabaseWatchlistRepository,
)
from app.infrastructure.realtime import OpenAIRealtimeSessionProvider
from app.infrastructure.seeds import load_preset_scenarios_seed
from app.infrastructure.sentiment import (
    AlternativeMeFearGreedProvider,
    FixtureFearGreedProvider,
    RoutingFearGreedProvider,
)
from app.infrastructure.stt import OpenAISTTProvider
from app.infrastructure.telegram import (
    BriefingCommandHandler,
    ChatMessageHandler,
    ImpactCommandHandler,
    SignalCommandHandler,
    SimulateCommandHandler,
    TelegramBotClient,
    TelegramBotRegistration,
)
from app.infrastructure.tts import OpenAITTSProvider
from app.infrastructure.universe import SupabaseInstrumentUniverse
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
        self._tts_provider: TTSProvider | None = None
        self._stt_provider: STTProvider | None = None
        self._embedding_provider: EmbeddingProvider | None = None
        self._vector_store: VectorStore | None = None
        self._agent_memory: AgentMemory | None = None
        self._conversation_repository: ConversationRepository | None = None
        self._watchlist_repository: WatchlistRepository | None = None
        self._note_repository: NoteRepository | None = None
        self._signal_repository: SignalRepository | None = None
        self._briefing_repository: BriefingRepository | None = None
        self._news_provider: NewsProvider | None = None
        self._news_item_repository: NewsItemRepository | None = None
        self._instrument_catalog_repository: InstrumentCatalogRepository | None = None
        self._instrument_universe: SupabaseInstrumentUniverse | None = None
        self._coingecko_search_provider: CoinGeckoSearchProvider | None = None
        self._search_coins_use_case: SearchCoins | None = None
        self._register_instrument_use_case: RegisterInstrument | None = None
        self._market_data_provider: MarketDataProvider | None = None
        self._macro_data_provider: MacroDataProvider | None = None
        self._fundamentals_provider: FundamentalsProvider | None = None
        self._chat_model: BaseChatModel | None = None
        self._chat_graph: Any | None = None
        self._agent_runner: AgentRunner | None = None
        self._realtime_session_provider: RealtimeSessionProvider | None = None
        self._generate_consequence_chain_use_case: GenerateConsequenceChain | None = None
        self._generate_conversation_title_use_case: GenerateConversationTitle | None = None
        self._notification_channel: NotificationChannel | None = None
        self._alerted_signal_tracker: AlertedSignalTracker | None = None
        self._telegram_link_repository: TelegramLinkRepository | None = None
        self._telegram_link_token_repository: TelegramLinkTokenRepository | None = None
        self._telegram_messenger: TelegramMessenger | None = None
        self._link_telegram_account_use_case: LinkTelegramAccount | None = None
        self._user_bot_repository: UserBotRepository | None = None
        self._bot_registration: BotRegistrationPort | None = None
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
        self._chart_config: ChartConfig | None = None
        self._build_price_chart_use_case: BuildPriceChart | None = None
        self._build_comparison_chart_use_case: BuildComparisonChart | None = None
        self._build_drawdown_chart_use_case: BuildDrawdownChart | None = None
        self._build_distribution_chart_use_case: BuildDistributionChart | None = None
        self._build_macro_chart_use_case: BuildMacroChart | None = None
        self._build_sentiment_gauge_use_case: BuildSentimentGauge | None = None
        self._render_chart_use_case: RenderChart | None = None

    def get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = OpenAIProvider(
                api_key=self._settings.openai_api_key, model=self._settings.openai_model
            )
        return self._llm_provider

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
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._watchlist_repository

    def get_note_repository(self) -> NoteRepository:
        """Return the cached per-user NoteRepository (issue #62), Supabase-backed with the
        same retry/config wiring as the other per-user repositories."""
        if self._note_repository is None:
            self._note_repository = SupabaseNoteRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
                retry_max_attempts=self._settings.supabase_retry_max_attempts,
                retry_backoff_base_seconds=self._settings.supabase_retry_backoff_base_seconds,
            )
        return self._note_repository

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

        `TelegramNotificationChannel` when `TELEGRAM_BOT_TOKEN` is configured (issue #14);
        `LoggingNotificationChannel` (no-op/logging stand-in) otherwise — same
        "graceful degradation when unconfigured" pattern as `get_agent_memory`'s Redis
        fallback and `get_news_provider`'s per-key-gated fan-out. Nothing in
        `application/` or `api/` needs to know which adapter is behind the port.
        """
        if self._notification_channel is None:
            messenger = self.get_telegram_messenger()
            if messenger is not None:
                self._notification_channel = TelegramNotificationChannel(
                    messenger=messenger,
                    watchlist_repository=self.get_watchlist_repository(),
                    telegram_link_repository=self.get_telegram_link_repository(),
                )
            else:
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

    def get_user_bot_repository(self) -> UserBotRepository:
        """Return the cached `UserBotRepository` backed by Supabase."""
        if self._user_bot_repository is None:
            self._user_bot_repository = SupabaseUserBotRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
            )
        return self._user_bot_repository

    def get_bot_registration(self) -> BotRegistrationPort:
        """Return the cached `BotRegistrationPort` for registering user-owned bots."""
        if self._bot_registration is None:
            self._bot_registration = TelegramBotRegistration(
                repository=self.get_user_bot_repository(),
                webhook_base_url=self._settings.telegram_webhook_url or "",
            )
        return self._bot_registration

    def get_briefing_command_handler(self) -> BriefingCommandHandler | None:
        """Return the cached `/briefing` command handler, or `None` when Telegram isn't
        configured — same unconfigured-integration fallback shape as
        `get_link_telegram_account_use_case` (issue #19).
        """
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._briefing_command_handler is None:
            self._briefing_command_handler = BriefingCommandHandler(
                link_repository=self.get_telegram_link_repository(),
                watchlist_repository=self.get_watchlist_repository(),
                briefing_repository=self.get_briefing_repository(),
                messenger=messenger,
                frontend_base_url=self._settings.frontend_base_url,
            )
        return self._briefing_command_handler

    def get_signal_command_handler(self) -> SignalCommandHandler | None:
        """Return the cached `/signal <TICKER>` command handler, or `None` when
        Telegram isn't configured (issue #19)."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._signal_command_handler is None:
            self._signal_command_handler = SignalCommandHandler(
                link_repository=self.get_telegram_link_repository(),
                instrument_universe=self.get_instrument_universe(),
                signal_repository=self.get_signal_repository(),
                messenger=messenger,
            )
        return self._signal_command_handler

    def get_simulate_command_handler(self) -> SimulateCommandHandler | None:
        """Return the cached `/simular <text>` command handler, or `None` when
        Telegram isn't configured (issue #19). Reuses the same cached
        `ScenarioSimulationRunner` as `POST /api/v1/scenarios/generate` and the
        `run_scenario_simulation` chat tool — see `get_scenario_simulation_runner`.
        """
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._simulate_command_handler is None:
            self._simulate_command_handler = SimulateCommandHandler(
                link_repository=self.get_telegram_link_repository(),
                scenario_simulation_runner=self.get_scenario_simulation_runner(),
                messenger=messenger,
                frontend_base_url=self._settings.frontend_base_url,
                default_locale=self._settings.default_locale,
            )
        return self._simulate_command_handler

    def get_impact_command_handler(self) -> ImpactCommandHandler | None:
        """Return the cached `/impact <sector>` command handler, or `None` when
        Telegram isn't configured — same pattern as `get_briefing_command_handler`."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._impact_command_handler is None:
            self._impact_command_handler = ImpactCommandHandler(
                event_repository=self.get_event_repository(),
                analyze_event_impact=AnalyzeEventImpact(
                    analyzer=self.get_event_analyzer(),
                ),
                messenger=messenger,
            )
        return self._impact_command_handler

    def get_chat_message_handler(self) -> ChatMessageHandler | None:
        """Return the cached conversational chat handler, or `None` when Telegram
        isn't configured — same pattern as `get_briefing_command_handler`."""
        messenger = self.get_telegram_messenger()
        if messenger is None:
            return None
        if self._chat_message_handler is None:
            self._chat_message_handler = ChatMessageHandler(
                agent_runner=self.get_agent_runner(),
                messenger=messenger,
            )
        return self._chat_message_handler

    def get_news_provider(self) -> NewsProvider:
        """Return the aggregated news source for the radar/agents.

        Fans out to every configured live source (Marketaux, NewsAPI, Finnhub, RSS, SEC
        EDGAR filings) concurrently; a source with no API key configured (or, for EDGAR,
        disabled/no feed URLs configured) is left out of the fan-out entirely. Falls back
        to `FixtureNewsProvider` whenever no live source is configured, or all of them
        fail / return nothing — see `AggregatingNewsProvider` for the merge/dedupe/link/
        filter pipeline.
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

            fixture_provider = FixtureNewsProvider(seed_path=self._settings.news_fixture_seed_path)
            self._news_provider = AggregatingNewsProvider(
                providers=live_providers,
                fixture_provider=fixture_provider,
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

    def get_coingecko_search_provider(self) -> CoinGeckoSearchProvider:
        """Return the cached CoinGecko `/search` adapter (issue #60 candidate resolution).

        Reuses the same base URL, API key, and cooldown settings as
        `get_market_data_provider`'s `CoinGeckoMarketDataProvider` — same vendor, same
        graceful rate-limit degradation (429/timeout -> `[]`, see
        `CoinGeckoCoinSearchProvider`'s docstring), just a different endpoint.
        """
        if self._coingecko_search_provider is None:
            self._coingecko_search_provider = CoinGeckoCoinSearchProvider(
                base_url=self._settings.coingecko_base_url,
                api_key=self._settings.coingecko_api_key,
                cooldown_seconds=self._settings.coingecko_cooldown_seconds,
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

    def get_market_data_provider(self) -> MarketDataProvider:
        """Return the routing MarketDataProvider (CoinGecko/yfinance + fixture fallback).

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
            fixture_provider = FixtureMarketDataProvider()
            self._market_data_provider = RoutingMarketDataProvider(
                yfinance_provider=YFinanceMarketDataProvider(symbol_overrides=yfinance_overrides),
                coingecko_provider=CoinGeckoMarketDataProvider(
                    base_url=self._settings.coingecko_base_url,
                    coingecko_id_overrides=coingecko_overrides,
                    cache_ttl_seconds=self._settings.coingecko_cache_ttl_seconds,
                    api_key=self._settings.coingecko_api_key,
                    cooldown_seconds=self._settings.coingecko_cooldown_seconds,
                ),
                fixture_provider=fixture_provider,
            )
        return self._market_data_provider

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
                llm_provider=self.get_llm_provider()
            )
        return self._generate_consequence_chain_use_case

    def get_generate_conversation_title_use_case(self) -> GenerateConversationTitle:
        """Return the cached conversation-title generator (issue #53 backend half).

        Reuses the `LLMProvider` port and injects the top-level Midas persona as the
        voice preamble, so titles carry the same voice while `application/` stays free
        of any infrastructure persona import. Backs `POST /api/v1/chat/title`.
        """
        if self._generate_conversation_title_use_case is None:
            self._generate_conversation_title_use_case = GenerateConversationTitle(
                llm_provider=self.get_llm_provider(),
                voice_preamble=MIDAS_PERSONA,
            )
        return self._generate_conversation_title_use_case

    def get_macro_data_provider(self) -> MacroDataProvider:
        """Return the routing MacroDataProvider (FRED rates/CPI + yfinance VIX + fixture fallback).

        `FRED_API_KEY` gates live rates/CPI (VIX needs no key); any live failure — including a
        missing key — falls back to `FixtureMacroDataProvider`, per method. See
        `infrastructure/macro/routing_macro_data_provider.py`.
        """
        if self._macro_data_provider is None:
            indicator_series_ids = {
                MacroIndicator.RATES: self._settings.fred_rates_series_id,
                MacroIndicator.CPI: self._settings.fred_cpi_series_id,
                MacroIndicator.GOLD: self._settings.fred_gold_series_id,
                MacroIndicator.OIL: self._settings.fred_oil_series_id,
                MacroIndicator.TREASURY_10Y: self._settings.fred_treasury_10y_series_id,
            }
            indicator_fixture_values = {
                MacroIndicator.RATES: self._settings.fixture_macro_rate,
                MacroIndicator.CPI: self._settings.fixture_macro_cpi,
                MacroIndicator.GOLD: self._settings.fixture_macro_gold,
                MacroIndicator.OIL: self._settings.fixture_macro_oil,
                MacroIndicator.TREASURY_10Y: self._settings.fixture_macro_treasury_10y,
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
            )
            fixture_provider = FixtureMacroDataProvider(
                rates_series_id=self._settings.fred_rates_series_id,
                cpi_series_id=self._settings.fred_cpi_series_id,
                fixture_rate=self._settings.fixture_macro_rate,
                fixture_cpi=self._settings.fixture_macro_cpi,
                fixture_vix=self._settings.fixture_macro_vix,
                low_threshold=self._settings.vix_low_threshold,
                elevated_threshold=self._settings.vix_elevated_threshold,
                high_threshold=self._settings.vix_high_threshold,
                indicator_series_ids=indicator_series_ids,
                indicator_fixture_values=indicator_fixture_values,
            )
            self._macro_data_provider = RoutingMacroDataProvider(
                live_provider=live_provider, fixture_provider=fixture_provider
            )
        return self._macro_data_provider

    def get_interpret_macro_event_use_case(self) -> InterpretMacroEvent:
        """Return the cached Macro Analyst use case (issue #21).

        Shared between the `macro` chat specialist's tool (`_get_chat_graph` below, via
        `build_macro_tools`) and `POST /api/v1/macro/interpret`
        (`api/v1/dependencies/get_interpret_macro_event_use_case.py`) — both surfaces call
        the exact same `InterpretMacroEvent.execute(event_description)`, grounded in the
        same `get_macro_data_provider()` instance every other macro-aware pipeline uses.
        """
        if self._interpret_macro_event_use_case is None:
            self._interpret_macro_event_use_case = InterpretMacroEvent(
                macro_data_provider=self.get_macro_data_provider(),
                llm_provider=self.get_llm_provider(),
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
            )
        return self._event_analyzer

    def get_event_repository(self) -> EventRepositoryPort:
        """Return the cached in-memory event repository for the Sentinel pipeline.

        Always `MemoryEventRepository` today — no Supabase adapter is wired yet.
        Swap this method to gate on a future `Settings` field (e.g. a Supabase
        connection) once a real adapter lands, same "unconfigured -> in-memory
        fallback" pattern as `get_agent_memory`'s Redis gate.
        """
        if self._event_repository is None:
            self._event_repository = MemoryEventRepository()
        return self._event_repository

    def get_event_news_provider(self) -> NewsProviderPort:
        """Return the cached demo news provider for the Sentinel pipeline.

        Always `DemoNewsProvider` today — swap to a real provider (e.g.
        YahooNewsProvider) once implemented, gated by a `Settings` field.
        """
        if self._event_news_provider is None:
            self._event_news_provider = DemoNewsProvider()
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

    def get_fear_greed_provider(self) -> FearGreedProvider:
        """Return the routing FearGreedProvider (alternative.me + fixture fallback).

        No API key required for the live adapter; any failure (network error, malformed
        payload, unrecognized classification label) falls back to
        `FixtureFearGreedProvider` — see `infrastructure/sentiment/routing_fear_greed_provider.py`.
        """
        if self._fear_greed_provider is None:
            live_provider = AlternativeMeFearGreedProvider(
                base_url=self._settings.alternative_me_base_url,
                timeout_seconds=self._settings.alternative_me_timeout_seconds,
            )
            fixture_provider = FixtureFearGreedProvider(
                fixture_value=self._settings.fixture_fear_greed_value,
                fixture_classification=self._settings.fixture_fear_greed_classification,
            )
            self._fear_greed_provider = RoutingFearGreedProvider(
                live_provider=live_provider, fixture_provider=fixture_provider
            )
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
                llm_provider=self.get_llm_provider(),
                bullish_threshold=self._settings.sentiment_bullish_threshold,
                bearish_threshold=self._settings.sentiment_bearish_threshold,
            )
        return self._analyze_sentiment_use_case

    def get_fundamentals_provider(self) -> FundamentalsProvider:
        """Return the routing FundamentalsProvider (yfinance + fixture fallback).

        Any live `yfinance` failure falls back to `FixtureFundamentalsProvider`, per method —
        see `infrastructure/fundamentals/routing_fundamentals_provider.py`.
        """
        if self._fundamentals_provider is None:
            risk_window_days = self._settings.upcoming_earnings_risk_window_days
            self._fundamentals_provider = RoutingFundamentalsProvider(
                live_provider=YFinanceFundamentalsProvider(risk_window_days=risk_window_days),
                fixture_provider=FixtureFundamentalsProvider(risk_window_days=risk_window_days),
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
                llm_provider=self.get_llm_provider(),
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
                llm_provider=self.get_llm_provider(),
                instrument_universe=self.get_instrument_universe(),
                max_synthesis_attempts=self._settings.scenario_synthesis_max_attempts,
            )
            graph = build_scenario_graph(
                normalize_scenario_intake=normalize_intake,
                gather_scenario_context=gather_context,
                generate_consequence_chain=self.get_generate_consequence_chain_use_case(),
                compute_scenario_quantification=compute_quantification,
                synthesize_scenario_result=synthesize_result,
                scenario_repository=self.get_scenario_repository(),
            )
            self._scenario_simulation_runner = ScenarioSimulationRunner(graph=graph)
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
        repo/LLM + the analog RAG pair) exactly as `api/v1/routers/signals.py` builds it
        per-request — the collaborators it depends on are themselves cached singletons, so
        the only per-call cost is wiring a thin orchestrator. Shared by the signals router
        and the `generate_signal` realtime tool so both run the identical pipeline.
        """
        return GenerateSignal(
            news_provider=self.get_news_provider(),
            market_data_provider=self.get_market_data_provider(),
            instrument_universe=self.get_instrument_universe(),
            signal_repository=self.get_signal_repository(),
            llm_provider=self.get_llm_provider(),
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
        )

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
            # Signal-only grounding: see `build_advisor_grounding_tools`'s docstring for
            # why briefing/watchlist grounding tools were removed (unauthenticated chat
            # route + no per-user ownership check would leak cross-tenant data). The
            # Scenario Simulation tool is safe to add on top — `ScenarioResult`s aren't
            # per-user data either (see `ScenarioRepository`'s docstring) — so it's kept
            # in its own builder (`build_scenario_tools`, not "grounding") and
            # concatenated here rather than folded into `build_advisor_grounding_tools`.
            advisor_tools = (
                build_advisor_grounding_tools(signal_repository=self.get_signal_repository())
                + build_scenario_tools(
                    scenario_simulation_runner=self.get_scenario_simulation_runner(),
                    default_locale=self._settings.default_locale,
                )
                + build_event_intelligence_tools(
                    event_repository=self.get_event_repository(),
                )
            )
            consequence_tools = build_consequence_tools(
                use_case=self.get_generate_consequence_chain_use_case()
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
            macro_tools = build_macro_tools(use_case=self.get_interpret_macro_event_use_case())
            sentiment_tools = build_sentiment_tools(use_case=self.get_analyze_sentiment_use_case())
            analyst_tools = build_analyst_grounding_tools(
                news_provider=self.get_news_provider(),
                generate_signal=self.get_generate_signal_use_case(),
                default_locale=self._settings.default_locale,
            )
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
                    )
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
                self._get_chat_model(),
                checkpointer,
                advisor_tools=advisor_tools,
                analyst_tools=analyst_tools,
                consequence_tools=consequence_tools,
                macro_tools=macro_tools,
                quant_tools=quant_tools,
                sentiment_tools=sentiment_tools,
            )
        return self._chat_graph


@lru_cache
def get_container() -> Container:
    """Return a process-wide cached Container, built from the cached Settings."""
    return Container(settings=get_settings())
