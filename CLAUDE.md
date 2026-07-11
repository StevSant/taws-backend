# CLAUDE.md — taws-backend

Guidance for future Claude Code sessions working in this repo. Keep it practical; this
is a hackathon skeleton, not a framework.

## Architecture: hexagonal / clean architecture

Dependencies point **inward only**:

```
api → application → domain ← infrastructure
```

- `domain/` is PURE. No `fastapi`, `openai`, `redis`, `langgraph`, or any other vendor
  import may appear here — ever. It defines **entities** (plain dataclasses/pydantic
  models) and **ports** (`abc.ABC` + `@abstractmethod`).
- `application/` holds use cases that orchestrate ports via constructor injection.
  They know nothing about which adapter is behind a port.
- `infrastructure/` holds adapters that implement domain ports against a real vendor
  (OpenAI, Supabase, Redis, pgvector, LangGraph).
- `api/` is the only layer allowed to import FastAPI. Routers depend on use cases and
  ports (injected via `api/v1/dependencies/`), never on infrastructure classes
  directly.

**Rule of thumb:** if you're tempted to `import openai` (or fastapi, redis, langgraph)
inside `domain/` or `application/`, stop — that logic belongs in `infrastructure/` or
`api/` instead.

## Conventions (strict, don't deviate)

- **One class/function per file.** Never group multiple classes in one file — this
  applies everywhere, including entities and enums (e.g. `MessageRole` and `Message`
  are two separate files).
- **Package re-exports.** Every `__init__.py` re-exports its package's public symbols
  with `__all__`, so consumers import from the package, not the file:
  ```python
  # Good
  from app.infrastructure.llm import OpenAIProvider
  # Bad — reaches into the implementation file
  from app.infrastructure.llm.openai_provider import OpenAIProvider
  ```
  **When you add a new file, update the parent `__init__.py` in the same change.**
- **No hardcoded values.** Every URL, key, model name, or threshold comes from
  `Settings` (`app/core/config/settings.py`), which reads from `.env` via
  pydantic-settings. If you catch yourself writing a literal API URL, model string, or
  timeout — stop, add a field to `Settings`, wire it through `.env` and `.env.example`.
- **No tests during the hackathon.** Accepted risk (see the architecture spec's
  decision ledger). If a bug needs a regression test mid-hackathon, add a minimal
  `pytest` test next to the code under test — don't build out a suite.

## How to add things

### Add a new LLM provider (swap OpenAI → Anthropic/Gemini/Ollama)

1. Create `infrastructure/llm/<vendor>_provider.py` implementing `LLMProvider`
   (`complete()`, `stream()`). See `infrastructure/llm/anthropic_provider.py` for the
   stub shape.
2. Re-export it from `infrastructure/llm/__init__.py`.
3. In `core/di/container.py`, change `Container.get_llm_provider()` to return the new
   adapter (probably gated by a new `Settings` field, e.g. `llm_provider: str`).

Nothing in `application/` or `api/` needs to change — that's the point of the port.

### Add a new port + adapter (e.g. a new capability)

1. Define the abstract port in `domain/<feature>/ports/<name>.py` (`ABC` +
   `@abstractmethod`). Re-export from that package's `__init__.py`.
2. Implement one or more adapters in `infrastructure/<area>/<name>.py`. Re-export from
   that package's `__init__.py`.
3. Wire it into `core/di/container.py` with a `get_<name>()` accessor.
4. If a use case needs it, inject the port (not the adapter) into the use case's
   constructor.

### Add a new router

1. Create `api/v1/routers/<name>.py` with an `APIRouter`.
2. Re-export it (aliased, e.g. `router as <name>_router`) from
   `api/v1/routers/__init__.py`.
3. `include_router` it in `main.py`'s `create_app()`.
4. Add request/response schemas in `api/v1/schemas/` (one Pydantic model per file,
   re-exported).
5. Pull dependencies (current user, providers, repos) from `api/v1/dependencies/` —
   add a new `get_<thing>.py` there if needed, resolving via `core/di`.

## Environment / settings rule

`Settings` in `core/config/settings.py` is the only place env vars are read. Every
field must exist in `.env.example` with a placeholder and a short comment. `REDIS_URL`
is optional — leave it unset locally; `Container.get_agent_memory()` falls back to
`InMemoryCheckpointer` automatically when it's not configured.

## uv commands

```bash
uv sync                 # install/update deps from pyproject.toml + uv.lock
uv add <package>         # add a runtime dependency
uv add --dev <package>   # add a dev-only dependency (linters, type checkers)
uv remove <package>      # remove a dependency
uv run <command>         # run anything inside the project's venv, e.g.:
uv run uvicorn app.main:app --reload
uv run ruff check .
uv run ruff format .
uv run pyright
```

Never use bare `pip`, `python -m`, or a bare `python` invocation — always `uv run`.

## Streaming (SSE)

`POST /api/v1/chat/stream` returns `text/event-stream` frames (`data: <token>\n\n`,
ending with `data: [DONE]\n\n`). The Angular frontend reads this with `fetch` +
`ReadableStream`, not `EventSource` (so it can send a POST body). Keep new streaming
endpoints in this same shape unless there's a strong reason to change it.
