"""Фикстуры тестов.

Тесты — юнит-уровня: вместо PostgreSQL используется SQLite в памяти, а
зависимость ``get_db`` подменяется через ``app.dependency_overrides``. Поэтому
для прогона тестов не нужен Docker и запущенный PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 — регистрирует таблицы в metadata
from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Изолированная база SQLite в памяти на каждый тест.

    ``StaticPool`` + ``check_same_thread=False`` нужны потому, что TestClient
    выполняет запросы в отдельном потоке, а соединение должно быть общим.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient с подменённой зависимостью ``get_db``."""

    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
