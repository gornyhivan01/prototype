# syntax=docker/dockerfile:1

# --- 1. Сборка React SPA ------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend

# Сначала только манифесты: слой с npm ci кешируется, пока не меняется lock-файл.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- 2. Python-зависимости ----------------------------------------------
FROM python:3.12-slim AS deps
# TODO: при желании зафиксировать конкретную версию uv вместо latest.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-dev: в образ не попадают pytest/ruff/black.
# --no-install-project: сам проект не пакет (package = false), копируем код ниже.
RUN uv sync --locked --no-dev --no-install-project

# --- 3. Runtime ---------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Непривилегированный пользователь: процесс не должен работать от root.
RUN useradd --system --uid 10001 --create-home --home-dir /app appuser

COPY --from=deps /app/.venv /app/.venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY --from=frontend /build/frontend/dist ./frontend/dist

USER appuser
EXPOSE 8000

# Один воркер: state/nonce/verifier SSO хранятся в памяти процесса.
# Для нескольких воркеров нужен общий store (например, Redis).
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
