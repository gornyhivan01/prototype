"""Тесты аудита: запись в PostgreSQL и дублирование в лог."""

from __future__ import annotations

import logging
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.audit import AuditAction, add_entry, client_ip
from app.models import AuditLog

_USER: dict[str, Any] = {
    "email": "ivan.petrov@example.com",
    "full_name": "Иван Петров",
    "password": "secret123",
}


def _create_user(client: TestClient) -> dict[str, Any]:
    response = client.post("/users", json=_USER)
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, password: str = _USER["password"]) -> Any:
    return client.post(
        "/auth/login",
        data={"username": _USER["email"], "password": password},
    )


def _count_entries(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(AuditLog)) or 0


def test_create_user_writes_audit_entry(client: TestClient, db_session: Session) -> None:
    """Регистрация сохраняет событие user.created."""
    user = _create_user(client)

    entry = db_session.scalar(select(AuditLog))

    assert entry is not None
    assert entry.action == AuditAction.USER_CREATED
    assert entry.actor_id == user["id"]
    assert entry.target_user_id == user["id"]
    assert entry.email == _USER["email"]
    assert entry.ip_address == "testclient"
    assert entry.details is None
    assert entry.created_at is not None


def test_create_user_logs_audit_without_password(client: TestClient, caplog: Any) -> None:
    """Событие дублируется в лог, но пароль туда не попадает."""
    with caplog.at_level(logging.INFO, logger="app.audit"):
        _create_user(client)

    assert "action=user.created" in caplog.text
    assert _USER["email"] in caplog.text
    assert _USER["password"] not in caplog.text


def test_duplicate_email_is_logged_but_not_saved(
    client: TestClient, db_session: Session, caplog: Any
) -> None:
    """Повторная регистрация откатывается и оставляет только warning."""
    _create_user(client)
    before = _count_entries(db_session)

    with caplog.at_level(logging.WARNING, logger="app.audit"):
        response = client.post("/users", json=_USER)

    assert response.status_code == 409
    assert _count_entries(db_session) == before
    assert "action=user.created result=rejected" in caplog.text
    assert "reason=duplicate_email" in caplog.text


def test_login_success_writes_audit_entry(client: TestClient, db_session: Session) -> None:
    """Успешный вход сохраняет событие auth.login.success."""
    user = _create_user(client)
    assert _login(client).status_code == 200

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.LOGIN_SUCCESS)
    ).one()

    assert entry.actor_id == user["id"]
    assert entry.target_user_id == user["id"]
    assert entry.email == _USER["email"]
    assert entry.details is None


def test_login_failure_writes_audit_entry(client: TestClient, db_session: Session) -> None:
    """Неверный пароль сохраняет событие auth.login.failed с причиной."""
    _create_user(client)
    response = _login(client, password="wrong-password")  # noqa: S106 — тестовые данные
    assert response.status_code == 401

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.LOGIN_FAILED)
    ).one()

    assert entry.actor_id is None
    assert entry.target_user_id is None
    assert entry.email == _USER["email"]
    assert entry.details == {"reason": "invalid_password"}


def test_login_unknown_email_writes_audit_entry(client: TestClient, db_session: Session) -> None:
    """Неизвестный email тоже попадает в аудит."""
    response = client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "secret123"},
    )

    assert response.status_code == 401
    entry = db_session.scalar(select(AuditLog))
    assert entry is not None
    assert entry.email == "nobody@example.com"
    assert entry.details == {"reason": "unknown_email"}


def test_login_with_long_username_truncates_audit_email(
    client: TestClient, db_session: Session
) -> None:
    """Слишком длинный username обрезается под размер колонки."""
    long_email = "a" * 1000

    response = client.post(
        "/auth/login",
        data={"username": long_email, "password": "secret123"},
    )

    assert response.status_code == 401
    entry = db_session.scalar(select(AuditLog))
    assert entry is not None
    assert entry.email == long_email[:320]


def test_audit_does_not_store_password_or_token(client: TestClient, db_session: Session) -> None:
    """В аудите нет ни пароля, ни access-токена."""
    _create_user(client)
    token = _login(client).json()["access_token"]

    entries = db_session.scalars(select(AuditLog)).all()
    dump = " ".join(
        str(getattr(entry, column.name))
        for entry in entries
        for column in AuditLog.__table__.columns
    )

    assert _USER["password"] not in dump
    assert token not in dump


def test_client_ip_returns_none_without_client() -> None:
    """Без объекта запроса или client IP не определяется."""
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    assert client_ip(None) is None
    assert client_ip(request) is None


def test_add_entry_normalizes_empty_email(db_session: Session) -> None:
    """Пустой email сохраняется как NULL, а не пустая строка."""
    empty = add_entry(db_session, action=AuditAction.USER_CREATED, email="")
    no_email = add_entry(db_session, action=AuditAction.USER_CREATED, email=None)
    db_session.commit()

    assert empty.email is None
    assert no_email.email is None
