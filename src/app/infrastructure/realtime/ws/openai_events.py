"""OpenAI Realtime WebSocket API event/type string constants — the single fix point.

Every literal the WS proxy sends to or matches from the OpenAI Realtime socket lives
here, so if OpenAI renames an event (the GA event names below are from research and
still need one live confirmation — see the module's callers' `[VERIFY LIVE]` notes),
the fix is a one-line change here instead of a hunt across the relay code.

Grouped by direction:
- ``*_CLIENT_*`` / builders: events the proxy SENDS to OpenAI.
- ``OPENAI_*``: server event ``type`` values the proxy RECEIVES from OpenAI.
"""

# --- Endpoint ---------------------------------------------------------------------
# Base Realtime WS URL; the model is appended as a `?model=` query param by the caller
# (kept here, not in Settings, since it is a fixed vendor endpoint, not a tunable).
OPENAI_REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"

# --- Audio format (both directions) -----------------------------------------------
AUDIO_FORMAT_PCM16 = "pcm16"

# --- Events the proxy SENDS to OpenAI ---------------------------------------------
CLIENT_SESSION_UPDATE = "session.update"
CLIENT_INPUT_AUDIO_APPEND = "input_audio_buffer.append"
CLIENT_CONVERSATION_ITEM_CREATE = "conversation.item.create"
CLIENT_RESPONSE_CREATE = "response.create"

# --- Server events the proxy RECEIVES from OpenAI ---------------------------------
# Handshake: emitted once when the session is ready; the proxy waits for it before
# sending the initial `session.update`.
OPENAI_SESSION_CREATED = "session.created"

# Assistant audio + transcript deltas relayed back to the browser.
OPENAI_OUTPUT_AUDIO_DELTA = "response.output_audio.delta"
OPENAI_OUTPUT_AUDIO_TRANSCRIPT_DELTA = "response.output_audio_transcript.delta"

# Turn / speaking lifecycle (barge-in + end-of-turn) used to drive the browser's
# speaking indicator.
OPENAI_SPEECH_STARTED = "input_audio_buffer.speech_started"
OPENAI_OUTPUT_AUDIO_DONE = "response.output_audio.done"
OPENAI_RESPONSE_DONE = "response.done"

# Errors surfaced by OpenAI on the session (e.g. malformed event we sent).
OPENAI_ERROR = "error"

# --- Item / function-call shape ---------------------------------------------------
# `response.done` carries a `response.output` list; a function call item has this type.
ITEM_TYPE_FUNCTION_CALL = "function_call"
# `conversation.item.create` payload type used to return a tool result to the model.
ITEM_TYPE_FUNCTION_CALL_OUTPUT = "function_call_output"
