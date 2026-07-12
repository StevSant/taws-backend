# taws-backend

FastAPI backend for the TAWS hackathon project — hexagonal/clean architecture skeleton
(domain ports, application use cases, infrastructure adapters, API layer), LangGraph +
OpenAI behind swappable ports, SSE streaming chat.

See `docs/specs/2026-07-11-taws-hackathon-architecture-design.md` in the root repo for
the full architecture rationale.

## Quickstart

```bash
# 1. Install dependencies (uv manages the venv for you)
uv sync

# 2. Copy the env template and fill in real values
cp .env.example .env

# 3. Run the dev server (auto-reload)
uv run uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`:

- `GET /health` — liveness probe
- `POST /api/v1/chat/stream` — SSE token stream (works without an OpenAI key: streams a
  placeholder reply so the endpoint never crashes before real keys are configured)

## Everyday commands

```bash
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pyright             # type-check
uv run uvicorn app.main:app --reload   # dev server

# Before a live demo: ingest current news and precompute linked Analyst signals
uv run python scripts/prepare_market_demo.py
```

No test suite during the hackathon (time-boxed, intentionally out of scope) — see
`CLAUDE.md` for details and where to add one later if a bug needs a regression test.

## Docker

```bash
docker build -t taws-backend .
docker run -p 8000:8000 --env-file .env taws-backend
```

Matches how AWS App Runner will run this image (listens on port 8000).

## Project layout

Hexagonal / Clean Architecture — dependencies point inward:
`api → application → domain ← infrastructure`. See `CLAUDE.md` for the full guide to
adding ports, adapters, and routers.
