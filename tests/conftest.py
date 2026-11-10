"""Фикстуры тестов: PostgreSQL, миграции Alembic, HTTP-клиент и токены.

По умолчанию база поднимается в Docker через Testcontainers. Если задана
переменная окружения ``TEST_DATABASE_URL`` (например, сервис ``postgres``
в CI), контейнер не запускается и используется указанная база.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # alembic-скрипты и пакет src импортируются относительно корня проекта.
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # testcontainers >= 4.13 перенесли модули в testcontainers.community
    from testcontainers.community.postgres import PostgresContainer
except ImportError:  # pragma: no cover - совместимость со старыми версиями
    from testcontainers.postgres import PostgresContainer

from tests.helpers import (  # noqa: E402 - импорт после правки sys.path
    login,
    promote_to_admin,
    register_and_login,
    register_user,
)

POSTGRES_IMAGE = os.environ.get("TEST_POSTGRES_IMAGE", "postgres:16-alpine")
USER_EMAIL = "user@example.com"
ADMIN_EMAIL = "admin@example.com"


def _apply_settings(database_url: str | None) -> None:
    """Подменяет ``DATABASE_URL`` и сбрасывает кэш настроек приложения."""
    from src.core.config import get_settings

    if database_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()


def _upgrade_database() -> None:
    """Применяет ``alembic upgrade head`` к тестовой базе.

    Alembic-окружение вызывает ``asyncio.run``, поэтому миграция выполняется
    в отдельном потоке: так она не трогает event loop, который pytest-asyncio
    готовит для тестов.
    """
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(command.upgrade, config, "head").result()

    # alembic.ini перенастраивает logging (root -> WARNING) и отключает уже
    # созданные логгеры, из-за чего logging.basicConfig(level=INFO) в src/main.py
    # становится no-op. Возвращаем уровень, который ожидает приложение.
    logging.getLogger().setLevel(logging.INFO)


async def _truncate_tables() -> None:
    """Очищает таблицы, чтобы тесты не влияли друг на друга."""
    from sqlalchemy import text

    from src.core.database import engine

    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE TABLE audit_log, refresh_tokens, tasks, users RESTART IDENTITY CASCADE")
        )


async def _dispose_engine() -> None:
    """Закрывает пул соединений после теста."""
    from src.core.database import engine

    await engine.dispose()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer | None]:
    """PostgreSQL в Docker для тестов; при ``TEST_DATABASE_URL`` не нужен."""
    if os.environ.get("TEST_DATABASE_URL"):
        yield None
        return

    container = PostgresContainer(POSTGRES_IMAGE, driver="asyncpg")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer | None) -> Iterator[str]:
    """URL тестовой базы со схемой, накатанной миграциями Alembic."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        assert postgres_container is not None, "нужен контейнер PostgreSQL или TEST_DATABASE_URL"
        url = postgres_container.get_connection_url()

    previous = os.environ.get("DATABASE_URL")
    _apply_settings(url)

    _upgrade_database()

    yield url

    _apply_settings(previous)


@pytest.fixture(scope="session")
def app(database_url: str) -> FastAPI:
    """Приложение FastAPI, настроенное на тестовую базу.

    Импорт отложен до запуска контейнера: ``src.core.database`` создаёт движок
    на уровне модуля и читает ``DATABASE_URL`` в момент импорта.
    """
    from src.main import app as application

    return application


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент поверх ASGI-приложения; база очищается перед каждым тестом."""
    await _truncate_tables()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await _dispose_engine()


@pytest.fixture
async def user_token(async_client: AsyncClient) -> str:
    """Токен обычного пользователя (роль USER)."""
    return await register_and_login(async_client, USER_EMAIL, name="Обычный пользователь")


@pytest.fixture
async def other_user_token(async_client: AsyncClient) -> str:
    """Токен второго обычного пользователя — для проверок доступа к чужим задачам."""
    return await register_and_login(async_client, "other@example.com", name="Другой пользователь")


@pytest.fixture
async def admin_token(async_client: AsyncClient) -> str:
    """Токен администратора (роль ADMIN)."""
    admin: dict[str, Any] = await register_user(async_client, ADMIN_EMAIL, name="Администратор")
    await promote_to_admin(admin["id"])
    return await login(async_client, ADMIN_EMAIL)
