"""Просмотр журнала аудита.

Администратор видит весь журнал (``GET /audit``), обычный пользователь —
только события своей учётки (``GET /audit/me``). Записи отдаются новыми
первыми, с фильтром по действию и постраничной выдачей.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.database import get_db
from app.dependencies import AdminUser, CurrentUser
from app.examples import (
    AUDIT_ACTION_EXAMPLES,
    AUDIT_EMAIL_EXAMPLES,
    AUDIT_PAGE_EXAMPLE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_RESPONSE,
)
from app.models import AuditLog, User
from app.schemas import AuditEntryRead, AuditPage

router = APIRouter(prefix="/audit", tags=["audit"])

DbSession = Annotated[Session, Depends(get_db)]

Limit = Annotated[int, Query(ge=1, le=200, description="Размер страницы (1–200)")]
Offset = Annotated[int, Query(ge=0, description="Сколько записей пропустить")]
ActionFilter = Annotated[
    str | None,
    Query(
        max_length=50,
        description="Точное имя действия, например `auth.login.success`",
        openapi_examples=AUDIT_ACTION_EXAMPLES,
    ),
]
EmailFilter = Annotated[
    str | None,
    Query(
        max_length=320,
        description="Подстрока email (регистронезависимо)",
        openapi_examples=AUDIT_EMAIL_EXAMPLES,
    ),
]


def _paginate(db: Session, query: Select, limit: int, offset: int) -> AuditPage:
    """Считает total по тем же условиям и возвращает страницу (новые первыми)."""
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    ).all()
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


@router.get(
    "",
    response_model=AuditPage,
    summary="Журнал аудита целиком (только для администратора)",
    description="""Возвращает весь журнал аудита, новые записи первыми.

Ручка защищена RBAC: доступна только пользователю с ролью `admin`.
Пароли и токены в журнал не попадают — только метаданные событий.

**Фильтры и страницы:**

- `action` — точное имя события (`user.created`, `user.deleted`,
  `auth.login.success`, `auth.login.failed`);
- `email` — подстрока email;
- `limit` / `offset` — постраничная выдача (по умолчанию 50, максимум 200).

**Пример запроса:**

```bash
curl 'http://localhost:8000/audit?action=auth.login.success&limit=20' \\
  -H 'Authorization: Bearer <admin-token>'
```
""",
    responses={
        200: {
            "description": "Страница журнала (новые записи первыми)",
            "content": {"application/json": {"example": AUDIT_PAGE_EXAMPLE}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: {"description": "Роль не позволяет смотреть журнал целиком"},
        422: VALIDATION_RESPONSE,
    },
)
def read_audit_log(
    db: DbSession,
    admin: AdminUser,
    action: ActionFilter = None,
    email: EmailFilter = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> AuditPage:
    """Возвращает весь журнал: фильтры по действию/email, новые первыми."""
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if email:
        query = query.where(AuditLog.email.ilike(f"%{email}%"))
    return _paginate(db, query, limit, offset)


@router.get(
    "/me",
    response_model=AuditPage,
    summary="Свои события в журнале аудита",
    description="""Возвращает события, связанные с текущим пользователем.

Это действия самого пользователя (например, входы в сервис) и события,
касающиеся его учётки (создание учётной записи администратором, неудачные
попытки входа с его email). Чужие события сюда не попадают — даже
администратору эту ручку можно использовать как «мой журнал».

**Пример запроса:**

```bash
curl 'http://localhost:8000/audit/me?limit=20' \\
  -H 'Authorization: Bearer <token>'
```
""",
    responses={
        200: {
            "description": "Страница событий пользователя (новые первыми)",
            "content": {"application/json": {"example": AUDIT_PAGE_EXAMPLE}},
        },
        401: UNAUTHORIZED_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def read_my_audit_log(
    db: DbSession,
    current_user: CurrentUser,
    action: ActionFilter = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> AuditPage:
    """События, которые совершил пользователь или которые касаются его учётки."""
    query = select(AuditLog).where(_own_events(current_user))
    if action:
        query = query.where(AuditLog.action == action)
    return _paginate(db, query, limit, offset)
