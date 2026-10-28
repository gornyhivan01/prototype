"""Эндпоинты работы с пользователями.

Создание и просмотр списка пользователей — только для администратора (RBAC,
роль приходит из Keycloak при SSO-входе). Свои собственные данные пользователь
видит через `GET /users/me`, а чужой профиль через `GET /users/{id}`
(админ или сам владелец).

Описания, примеры запросов и примеры ответов на русском языке отображаются в
Swagger UI на ``/docs``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import kc_admin
from app.audit import AuditAction, add_entry, log_entry, log_rejection
from app.database import get_db
from app.dependencies import AdminUser, CurrentUser
from app.examples import (
    CONFLICT_RESPONSE,
    CREATE_USER_EXAMPLES,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    USER_CREATED_EXAMPLE,
    USER_ID_EXAMPLES,
    VALIDATION_RESPONSE,
)
from app.kc_admin import KeycloakAdminError
from app.models import ROLE_ADMIN, User
from app.schemas import UserCreate, UserRead
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

# Annotated-стиль для зависимостей: не выполняется вызов в значении по умолчанию
# (в отличие от ``db: Session = Depends(get_db)``) и лучше типизируется.
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя (только для администратора)",
    description="""Создаёт пользователя и сохраняет его в PostgreSQL.

Ручка защищена RBAC: доступна только пользователю с ролью `admin`. Роль
задаётся полем `role` (по умолчанию `user`). Пользователь **синхронно
создаётся и в Keycloak** (SSO): той же почтой и паролем, ролью `admin`
выдаётся realm-роль `admin` — поэтому вход по `Войти через SSO` будет работать.

Если Keycloak недоступен, создание отменяется целиком — вернётся `503`,
чтобы не было «полупользователей» (в БД, но не в SSO).

Пароль принимается в открытом виде только в этом запросе и сразу превращается
в Argon2id-хеш — в базе и в ответах API пароля нет.

**Пример запроса:**

```bash
curl -X POST http://localhost:8000/users \\
  -H 'Authorization: Bearer <admin-token>' \\
  -H 'Content-Type: application/json' \\
  -d '{"email": "ivan.petrov@example.com", "full_name": "Иван Петров",
       "password": "secret123", "role": "user"}'
```

Поле `email` должно быть уникальным: повторная отправка того же адреса вернёт `409`.
""",
    responses={
        201: {
            "description": "Пользователь успешно создан и сохранён в базе",
            "content": {"application/json": {"example": USER_CREATED_EXAMPLE}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: {"description": "Роль не позволяет создавать пользователей"},
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def create_user(
    payload: Annotated[UserCreate, Body(openapi_examples=CREATE_USER_EXAMPLES)],
    db: DbSession,
    request: Request,
    admin: AdminUser,
) -> User:
    """Создаёт пользователя (в БД и в Keycloak); email должен быть уникальным."""
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()  # получаем id и проверяем уникальность email
    except IntegrityError:
        db.rollback()
        log_rejection(
            action=AuditAction.USER_CREATED.value,
            email=payload.email,
            request=request,
            reason="duplicate_email",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        ) from None

    # Синхронизация с Keycloak (SSO). Если IdP недоступен — откатываем всё,
    # чтобы не оставить пользователя без возможности SSO-входа.
    try:
        kc_admin.create_keycloak_user(
            email=payload.email,
            password=payload.password,
            full_name=user.full_name,
            role=user.role,
        )
    except KeycloakAdminError as exc:
        db.rollback()
        log_rejection(
            action=AuditAction.USER_CREATED.value,
            email=payload.email,
            request=request,
            reason=f"keycloak_sync_failed:{exc}",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось создать учётку SSO — пользователь не создан",
        ) from None

    entry = add_entry(
        db,
        action=AuditAction.USER_CREATED,
        actor_id=admin.id,
        target_user_id=user.id,
        email=user.email,
        request=request,
    )
    db.commit()
    db.refresh(user)
    log_entry(entry)
    return user


@router.get(
    "",
    response_model=list[UserRead],
    summary="Список пользователей (только для администратора)",
    description="""Возвращает всех пользователей из PostgreSQL.

Ручка защищена RBAC: доступна только пользователю с ролью `admin`.

**Пример запроса:**

```bash
curl http://localhost:8000/users -H 'Authorization: Bearer <admin-token>'
```
""",
    responses={
        200: {
            "description": "Список пользователей",
            "content": {"application/json": {"example": [USER_CREATED_EXAMPLE]}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: {"description": "Роль не позволяет просматривать пользователей"},
    },
)
def list_users(
    db: DbSession,
    admin: AdminUser,
) -> list[User]:
    """Возвращает всех пользователей (для администратора)."""
    users = db.scalars(select(User).order_by(User.id)).all()
    return list(users)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Текущий пользователь",
    description="""Возвращает пользователя, которому принадлежит access-токен.

Ручка защищена: нужен заголовок `Authorization: Bearer <token>`, который
выдаёт `POST /auth/login` или SSO-вход (`/auth/sso/start`). В Swagger UI
токен подставляется после нажатия **Authorize**.

**Пример запроса:**

```bash
curl http://localhost:8000/users/me -H 'Authorization: Bearer <token>'
```
""",
    responses={
        200: {
            "description": "Пользователь найден",
            "content": {"application/json": {"example": USER_CREATED_EXAMPLE}},
        },
        401: UNAUTHORIZED_RESPONSE,
    },
)
def read_current_user(current_user: CurrentUser) -> User:
    """Возвращает владельца access-токена."""
    return current_user


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Получить пользователя по id (себя или для администратора)",
    description="""Возвращает пользователя из PostgreSQL по идентификатору.

Доступна администратору или самому владельцу профиля. Для обычного
пользователя чужой профиль вернёт `403`.

**Пример запроса:**

```bash
curl http://localhost:8000/users/1 -H 'Authorization: Bearer <token>'
```

Если пользователя с таким id нет — вернётся `404`.
""",
    responses={
        200: {
            "description": "Пользователь найден",
            "content": {"application/json": {"example": USER_CREATED_EXAMPLE}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: {"description": "Недостаточно прав для просмотра чужого профиля"},
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def read_user(
    user_id: Annotated[
        int,
        Path(description="Идентификатор пользователя", openapi_examples=USER_ID_EXAMPLES),
    ],
    db: DbSession,
    current_user: CurrentUser,
) -> User:
    """Возвращает пользователя: администратору или владельцу; иначе 403/404."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    if current_user.role != ROLE_ADMIN and current_user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав",
        )
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Удалить пользователя (только для администратора)",
    description="""Удаляет пользователя из PostgreSQL.

Ручка защищена RBAC: доступна только пользователю с ролью `admin`.
Удалить собственную учётку нельзя — это защита от блокировки самого себя.
Учётка так же удаляется из Keycloak (SSO); если IdP недоступен — вернётся
`503` и ничего не будет удалено.
Записи аудита этого пользователя сохраняются (FK `ON DELETE SET NULL`),
удаляется только сам пользователь.

**Пример запроса:**

```bash
curl -X DELETE http://localhost:8000/users/2 \\
  -H 'Authorization: Bearer <admin-token>'
```
""",
    responses={
        204: {"description": "Пользователь удалён"},
        400: {"description": "Нельзя удалить собственную учётку"},
        401: UNAUTHORIZED_RESPONSE,
        403: {"description": "Роль не позволяет удалять пользователей"},
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def delete_user(
    user_id: Annotated[
        int,
        Path(description="Идентификатор пользователя", openapi_examples=USER_ID_EXAMPLES),
    ],
    db: DbSession,
    request: Request,
    admin: AdminUser,
) -> None:
    """Удаляет пользователя; аудит действия сохраняется."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить собственную учётку",
        )

    # Сначала синхронизация с Keycloak (SSO): не удаляем локально, если
    # IdP не дал удалить учётку, — иначе SSO-учётка останется бесхозной.
    try:
        kc_admin.delete_keycloak_user(user.email)
    except KeycloakAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось удалить учётку SSO — пользователь не удалён",
        ) from exc

    entry = add_entry(
        db,
        action=AuditAction.USER_DELETED,
        actor_id=admin.id,
        target_user_id=user.id,
        email=user.email,
        request=request,
        details={"deleted": user.email},
    )
    db.delete(user)
    db.commit()
    log_entry(entry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
