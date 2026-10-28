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

    # --- SSO / Keycloak (OIDC) ---
    # Включает ручки /auth/sso/*. Парольный /auth/login при этом продолжает
    # работать: гибридный режим. Чтобы оставить только SSO, задайте
    # SSO_ONLY=true (проверка добавляется в login).
    sso_enabled: bool = True
    sso_only: bool = False
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "prototype"
    keycloak_client_id: str = "prototype-web"
    keycloak_client_secret: str = "prototype-web-secret"  # noqa: S105 — dev-секрет
    sso_redirect_uri: str = "http://localhost:8000/auth/sso/callback"
    # Куда Keycloak вернёт после single logout. Должен быть в списке
    # postLogoutRedirectUris клиента (keycloak/realm-export.json).
    sso_post_logout_redirect_uri: str = "http://localhost:8000/"
    # Учётка админа Keycloak для Admin REST (создание/удаление пользователей
    # синхронно с SSO). Только для разработки; задаётся через .env.
    keycloak_admin_user: str = "admin"
    keycloak_admin_password: str = "admin"  # noqa: S105 — dev-админ Keycloak (docker-compose)


@lru_cache
def get_settings() -> Settings:
    """Возвращает синглтон настроек (читает окружение один раз)."""
    return Settings()
