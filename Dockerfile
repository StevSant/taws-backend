# syntax=docker/dockerfile:1

# ---- builder: resolve deps with uv into a venv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---- runtime: slim image, just the venv + source ----
FROM python:3.12-slim-bookworm AS runtime

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

USER appuser

# Configurable via env so this image isn't tied to one platform's port convention (App
# Runner, local docker run, etc. can each set HOST/PORT without an image rebuild) — same
# "no hardcoded values" rule the app's own `Settings` class follows. Defaults match App
# Runner's default listening port (8000, as configured on the service).
ENV HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# Shell form so $HOST/$PORT are expanded at container start; `exec` replaces the shell
# process with uvicorn (instead of running it as a child) so SIGTERM reaches uvicorn
# directly for a clean shutdown, rather than the shell swallowing it until Docker's stop
# timeout forces a SIGKILL.
CMD exec uvicorn app.main:app --host "$HOST" --port "$PORT"
