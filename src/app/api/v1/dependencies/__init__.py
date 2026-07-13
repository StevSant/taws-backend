from app.api.v1.dependencies.decode_bearer_token import decode_bearer_token
from app.api.v1.dependencies.decode_unverified_identity import decode_unverified_identity
from app.api.v1.dependencies.dev_fallback_allowed import dev_fallback_allowed
from app.api.v1.dependencies.dev_fallback_user import DEV_FALLBACK_USER
from app.api.v1.dependencies.get_agent_runner import get_agent_runner
from app.api.v1.dependencies.get_alerted_signal_tracker import get_alerted_signal_tracker
from app.api.v1.dependencies.get_analyze_pending_news_use_case import (
    get_analyze_pending_news_use_case,
)
from app.api.v1.dependencies.get_analyze_sentiment_use_case import get_analyze_sentiment_use_case
from app.api.v1.dependencies.get_bot_registration import get_bot_registration
from app.api.v1.dependencies.get_briefing_command_handler import get_briefing_command_handler
from app.api.v1.dependencies.get_briefing_document_renderer import get_briefing_document_renderer
from app.api.v1.dependencies.get_briefing_repository import get_briefing_repository
from app.api.v1.dependencies.get_chat_message_handler import get_chat_message_handler
from app.api.v1.dependencies.get_conversation_repository import get_conversation_repository
from app.api.v1.dependencies.get_email_sender import get_email_sender
from app.api.v1.dependencies.get_embedding_provider import get_embedding_provider
from app.api.v1.dependencies.get_fast_llm_provider import get_fast_llm_provider
from app.api.v1.dependencies.get_fear_greed_provider import get_fear_greed_provider
from app.api.v1.dependencies.get_force_analyze_news_item_use_case import (
    get_force_analyze_news_item_use_case,
)
from app.api.v1.dependencies.get_fundamentals_provider import get_fundamentals_provider
from app.api.v1.dependencies.get_generate_consequence_chain_use_case import (
    get_generate_consequence_chain_use_case,
)
from app.api.v1.dependencies.get_generate_conversation_title_use_case import (
    get_generate_conversation_title_use_case,
)
from app.api.v1.dependencies.get_generate_signal_use_case import get_generate_signal_use_case
from app.api.v1.dependencies.get_impact_command_handler import get_impact_command_handler
from app.api.v1.dependencies.get_instrument_universe import get_instrument_universe
from app.api.v1.dependencies.get_interpret_macro_event_use_case import (
    get_interpret_macro_event_use_case,
)
from app.api.v1.dependencies.get_link_telegram_account_use_case import (
    get_link_telegram_account_use_case,
)
from app.api.v1.dependencies.get_macro_data_provider import get_macro_data_provider
from app.api.v1.dependencies.get_market_data_provider import get_market_data_provider
from app.api.v1.dependencies.get_market_pulse_use_case import get_market_pulse_use_case
from app.api.v1.dependencies.get_news_item_repository import get_news_item_repository
from app.api.v1.dependencies.get_news_prefilter_policy import get_news_prefilter_policy
from app.api.v1.dependencies.get_news_provider import get_news_provider
from app.api.v1.dependencies.get_note_repository import get_note_repository
from app.api.v1.dependencies.get_notification_channel import get_notification_channel
from app.api.v1.dependencies.get_preset_scenario_rows import get_preset_scenario_rows
from app.api.v1.dependencies.get_process_incoming_event_use_case import (
    get_process_incoming_event_use_case,
)
from app.api.v1.dependencies.get_realtime_session_provider import (
    get_realtime_session_provider,
)
from app.api.v1.dependencies.get_reasoning_llm_provider import get_reasoning_llm_provider
from app.api.v1.dependencies.get_refresh_tracked_analysis_use_case import (
    get_refresh_tracked_analysis_use_case,
)
from app.api.v1.dependencies.get_render_chart_use_case import get_render_chart_use_case
from app.api.v1.dependencies.get_reorder_watchlists_use_case import (
    get_reorder_watchlists_use_case,
)
from app.api.v1.dependencies.get_resolve_locale_use_case import get_resolve_locale_use_case
from app.api.v1.dependencies.get_scenario_repository import get_scenario_repository
from app.api.v1.dependencies.get_scenario_simulation_runner import get_scenario_simulation_runner
from app.api.v1.dependencies.get_sentiment_repository import get_sentiment_repository
from app.api.v1.dependencies.get_signal_command_handler import get_signal_command_handler
from app.api.v1.dependencies.get_signal_repository import get_signal_repository
from app.api.v1.dependencies.get_simulate_command_handler import get_simulate_command_handler
from app.api.v1.dependencies.get_stt_provider import get_stt_provider
from app.api.v1.dependencies.get_telegram_link_repository import get_telegram_link_repository
from app.api.v1.dependencies.get_telegram_link_token_repository import (
    get_telegram_link_token_repository,
)
from app.api.v1.dependencies.get_telegram_messenger import get_telegram_messenger
from app.api.v1.dependencies.get_tts_provider import get_tts_provider
from app.api.v1.dependencies.get_user_bot_repository import get_user_bot_repository
from app.api.v1.dependencies.get_user_profile_repository import get_user_profile_repository
from app.api.v1.dependencies.get_vector_store import get_vector_store
from app.api.v1.dependencies.get_watchlist_repository import get_watchlist_repository
from app.api.v1.dependencies.jwks_client import get_jwks_client
from app.api.v1.dependencies.require_current_user import require_current_user
from app.api.v1.dependencies.require_role import require_compliance, require_role
from app.api.v1.dependencies.resolve_user_role import resolve_user_role
from app.api.v1.dependencies.supabase_jwks_url import supabase_jwks_url
from app.api.v1.dependencies.verify_realtime_ws_token import verify_realtime_ws_token

__all__ = [
    "DEV_FALLBACK_USER",
    "decode_bearer_token",
    "decode_unverified_identity",
    "dev_fallback_allowed",
    "get_agent_runner",
    "get_alerted_signal_tracker",
    "get_analyze_sentiment_use_case",
    "get_fear_greed_provider",
    "get_briefing_command_handler",
    "get_briefing_document_renderer",
    "get_chat_message_handler",
    "get_briefing_repository",
    "get_conversation_repository",
    "get_email_sender",
    "get_embedding_provider",
    "get_fundamentals_provider",
    "get_generate_consequence_chain_use_case",
    "get_generate_conversation_title_use_case",
    "get_impact_command_handler",
    "get_instrument_universe",
    "get_interpret_macro_event_use_case",
    "get_jwks_client",
    "get_link_telegram_account_use_case",
    "get_analyze_pending_news_use_case",
    "get_fast_llm_provider",
    "get_force_analyze_news_item_use_case",
    "get_generate_signal_use_case",
    "get_reasoning_llm_provider",
    "get_refresh_tracked_analysis_use_case",
    "get_sentiment_repository",
    "get_macro_data_provider",
    "get_market_pulse_use_case",
    "get_market_data_provider",
    "get_news_item_repository",
    "get_news_prefilter_policy",
    "get_news_provider",
    "get_notification_channel",
    "get_preset_scenario_rows",
    "get_process_incoming_event_use_case",
    "get_realtime_session_provider",
    "get_render_chart_use_case",
    "get_resolve_locale_use_case",
    "get_reorder_watchlists_use_case",
    "get_scenario_repository",
    "get_scenario_simulation_runner",
    "get_signal_command_handler",
    "get_signal_repository",
    "get_simulate_command_handler",
    "get_stt_provider",
    "get_bot_registration",
    "get_telegram_link_repository",
    "get_telegram_link_token_repository",
    "get_user_bot_repository",
    "get_user_profile_repository",
    "get_telegram_messenger",
    "get_tts_provider",
    "get_vector_store",
    "get_note_repository",
    "get_watchlist_repository",
    "require_compliance",
    "require_current_user",
    "require_role",
    "resolve_user_role",
    "supabase_jwks_url",
    "verify_realtime_ws_token",
]
