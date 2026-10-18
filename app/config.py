"""Настройки приложения через pydantic-settings.

Значения читаются из переменных окружения и файла ``.env``.
"""

from __future__ import annotations

from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    """Возвращает синглтон настроек (читает окружение один раз)."""
    return Settings()
