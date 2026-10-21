"""Настройки приложения через pydantic-settings.

Значения читаются из переменных окружения и файла ``.env``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервиса."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "FastAPI, PostgreSQL, Alembic"
    database_url: str = "postgresql+psycopg2://app:app@localhost:5433/app"
    debug: bool = False

    # --- JWT ---
    # В продакшене SECRET_KEY обязателен и должен быть случайным (>= 32 символов):
    # python -c "import secrets; print(secrets.token_urlsafe(32))"
    secret_key: str = "dev-secret-key-change-me-0123456789abcdef"  # noqa: S105
    jwt_algorithm: str = "HS256"
    # Больше нуля: токен с нулевым сроком жизни бесполезен, отрицательный —
    # сразу просрочен. Значение можно переопределить через .env.
    access_token_expire_minutes: int = Field(default=30, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Возвращает синглтон настроек (читает окружение один раз)."""
    return Settings()
