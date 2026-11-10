"""Просмотр журнала аудита.

Администратор видит весь журнал (``GET /audit``), обычный пользователь —
только события своей учётки (``GET /audit/me``). Записи отдаются новыми
первыми, с фильтром по действию и постраничной выдачей.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.api.dependencies import AdminUser, CurrentUser, DbSession
from src.api.schemas.audit import AuditEntryRead, AuditPage
from src.models.audit import AuditLog
from src.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])

Limit = Annotated[int, Query(ge=1, le=200, description="Размер страницы (1–200)")]
Offset = Annotated[int, Query(ge=0, description="Сколько записей пропустить")]
ActionFilter = Annotated[
    str | None,
    Query(max_length=50, description="Точное имя действия, например `auth.login.success`"),
]
EmailFilter = Annotated[
    str | None,
    Query(max_length=320, description="Подстрока email (регистронезависимо)"),
]


async def _paginate(
    session: AsyncSession, query: Select[tuple[AuditLog]], limit: int, offset: int
) -> AuditPage:
    """Считает total по тем же условиям и возвращает страницу (новые первыми)."""
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    )
    return AuditPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[AuditEntryRead.model_validate(row) for row in rows],
    )


def _own_events(user: User) -> ColumnElement[bool]:
    """Условия «своих» событий: действия пользователя и события о его учётке."""
    return or_(
        AuditLog.actor_id == user.id,
        AuditLog.target_user_id == user.id,
        and_(AuditLog.actor_id.is_(None), AuditLog.email == user.email),
    )


@router.get("", response_model=AuditPage, summary="Журнал аудита целиком (только ADMIN)")
async def read_audit_log(
    admin: AdminUser,
    session: DbSession,
    action: ActionFilter = None,
    email: EmailFilter = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> AuditPage:
    """Весь журнал: фильтры по действию/email, новые записи первыми."""
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if email:
        query = query.where(AuditLog.email.ilike(f"%{email}%"))
    return await _paginate(session, query, limit, offset)


@router.get("/me", response_model=AuditPage, summary="Свои события в журнале аудита")
async def read_my_audit_log(
    current_user: CurrentUser,
    session: DbSession,
    action: ActionFilter = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> AuditPage:
    """События, которые совершил пользователь или которые касаются его учётки."""
    query = select(AuditLog).where(_own_events(current_user))
    if action:
        query = query.where(AuditLog.action == action)
    return await _paginate(session, query, limit, offset)
