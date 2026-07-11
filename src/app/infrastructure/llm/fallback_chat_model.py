import itertools

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

_PLACEHOLDER_REPLY = (
    "[ChatModelFactory] No OPENAI_API_KEY configured — this is a placeholder reply "
    "so agent graphs keep streaming without a real key."
)


def build_fallback_chat_model() -> GenericFakeChatModel:
    """Build a chat model that streams a canned reply, used when no API key is set.

    `GenericFakeChatModel` splits its message content on whitespace and streams it
    chunk-by-chunk (see its `_stream`), so this still exercises token-by-token
    streaming through `stream_mode="messages"` in `chat_graph.build_chat_graph` — the
    graph/runner never special-case "no key" themselves. `itertools.cycle` keeps the
    message iterator alive across turns instead of raising `StopIteration` after the
    first call, since the compiled graph can be invoked many times per thread.
    """
    return GenericFakeChatModel(messages=itertools.cycle([_PLACEHOLDER_REPLY]))
