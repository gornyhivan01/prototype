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


# --- Роли и токены для RBAC-тестов ---

_ADMIN_EMAIL = "admin@example.com"
_ADMIN_PASSWORD = "password123"  # noqa: S105 — тестовый пароль
_USER_EMAIL = "user@example.com"
_USER_PASSWORD = "password123"  # noqa: S105 — тестовый пароль


def _token_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    """Проходит парольный вход и возвращает заголовок Authorization."""
    response = client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _make_admin(db: Session) -> None:
    from app.models import ROLE_ADMIN, User
    from app.security import hash_password

    db.add(
        User(
            email=_ADMIN_EMAIL,
            full_name="Админ для тестов",
            hashed_password=hash_password(_ADMIN_PASSWORD),
            role=ROLE_ADMIN,
        )
    )
    db.commit()


def _make_user(db: Session) -> None:
    from app.models import User
    from app.security import hash_password

    db.add(
        User(
            email=_USER_EMAIL,
            full_name="Обычный пользователь",
            hashed_password=hash_password(_USER_PASSWORD),
            role="user",
        )
    )
    db.commit()


@pytest.fixture
def admin_headers(client: TestClient, db_session: Session) -> dict[str, str]:
    """Заголовок Authorization администратора."""
    _make_admin(db_session)
    return _token_headers(client, _ADMIN_EMAIL, _ADMIN_PASSWORD)


@pytest.fixture
def user_headers(client: TestClient, db_session: Session) -> dict[str, str]:
    """Заголовок Authorization обычного пользователя."""
    _make_user(db_session)
    return _token_headers(client, _USER_EMAIL, _USER_PASSWORD)
