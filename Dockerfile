# syntax=docker/dockerfile:1

# --- 1. Сборка React SPA ------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend

# Сначала только манифесты: слой с npm ci кэшируется, пока не изменился lock-файл.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- 2. Зависимости Python ----------------------------------------------
FROM python:3.12-slim AS deps

# uv ставим из PyPI, а не из ghcr.io: сборка не зависит от доступности
# GitHub Container Registry (в закрытых сетях он часто заблокирован).
ENV PIP_NO_CACHE_DIR=1
RUN pip install uv==0.13.7

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-dev: в образ не попадают pytest/ruff/black.
# --no-install-project: проект не пакет (package = false), копировать нечего.
RUN uv sync --locked --no-dev --no-install-project

# --- 3. Runtime ---------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Непривилегированный пользователь: процесс не работает от root.
RUN useradd --system --uid 10001 --create-home --home-dir /app appuser

COPY --from=deps /app/.venv /app/.venv
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY --from=frontend /build/frontend/dist ./static

USER appuser
EXPOSE 8000

CMD ["uvicorn", "src.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
