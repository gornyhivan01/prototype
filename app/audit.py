"""Аудит действий пользователей: запись в PostgreSQL и stdout.

Пароли и JWT в аудит не попадают: фиксируются только метаданные события.
Запись добавляется в сессию SQLAlchemy, коммит выполняет вызывающий код —
так действие и его аудит попадают в одну транзакцию.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger("app.audit")


class AuditAction(StrEnum):
    """События, которые попадают в аудит."""

    USER_CREATED = "user.created"
    USER_DELETED = "user.deleted"  # задел на будущую ручку удаления
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILED = "auth.login.failed"


def client_ip(request: Request | None) -> str | None:
    """Возвращает IP клиента.

    За reverse-proxy здесь окажется адрес прокси: для реального IP нужен
    разбор ``X-Forwarded-For`` с доверенным списком прокси.
    """
    if request is None or request.client is None:
        return None
    return request.client.host


def _normalize_email(value: str | None) -> str | None:
    """Ограничивает email длиной колонки (на случай мусорного ввода)."""
    if not value:
        return None
    return value[:320]


def add_entry(
    db: Session,
    *,
    action: AuditAction,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    email: str | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Добавляет запись аудита в сессию (без коммита)."""
    entry = AuditLog(
        action=action.value,
        actor_id=actor_id,
        target_user_id=target_user_id,
        email=_normalize_email(email),
        ip_address=client_ip(request),
        details=details,
    )
    db.add(entry)
    return entry


def log_entry(entry: AuditLog) -> None:
    """Дублирует сохранённую запись в лог приложения (stdout)."""
    logger.info(
        "audit action=%s actor_id=%s target_user_id=%s email=%s ip=%s",
        entry.action,
        entry.actor_id,
        entry.target_user_id,
        entry.email,
        entry.ip_address,
    )


def log_rejection(
    *,
    action: str,
    email: str | None,
    request: Request | None,
    reason: str,
) -> None:
    """Пишет в лог событие, которое не сохраняется в БД.

    Например, попытка регистрации с занятым email: транзакция откатывается,
    поэтому запись аудита создавать некуда.
    """
    logger.warning(
        "audit action=%s result=rejected email=%s ip=%s reason=%s",
        action,
        _normalize_email(email),
        client_ip(request),
        reason,
    )
