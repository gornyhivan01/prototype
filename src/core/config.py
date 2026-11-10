"""Настройки приложения через pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервиса (читаются из переменных окружения и .env)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Prototype"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"

    secret_key: str = "dev-secret-key-change-me-0123456789abcdef"  # noqa: S105
    jwt_algorithm: str = "HS256"
    # Access-токен короткий: отозвать его нельзя, поэтому окно кражи мало́.
    access_token_expire_minutes: int = Field(default=15, gt=0)
    # Refresh-токен живёт в БД, ротируется при каждом обновлении и отзывается.
    refresh_token_expire_days: int = Field(default=7, gt=0)

    # Cookie-сессия. В продакшене: COOKIE_SECURE=true (только по HTTPS).
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "strict"


@lru_cache
def get_settings() -> Settings:
    """Возвращает синглтон настроек (читает окружение один раз)."""
    return Settings()
