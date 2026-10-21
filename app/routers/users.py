"""Эндпоинты работы с пользователями.

Описания, примеры запросов и примеры ответов на русском языке отображаются в
Swagger UI на ``/docs``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import CurrentUser
from app.examples import (
    CONFLICT_RESPONSE,
    CREATE_USER_EXAMPLES,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    USER_CREATED_EXAMPLE,
    USER_ID_EXAMPLES,
    VALIDATION_RESPONSE,
)
from app.models import User
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
    summary="Создать пользователя",
    description="""Создаёт пользователя и сохраняет его в PostgreSQL.

Пароль принимается в открытом виде только в этом запросе и сразу превращается
в Argon2id-хеш — в базе и в ответах API пароля нет.

**Пример запроса:**

```bash
curl -X POST http://localhost:8000/users \\
  -H 'Content-Type: application/json' \\
  -d '{"email": "ivan.petrov@example.com", "full_name": "Иван Петров", "password": "secret123"}'
```

Поле `email` должно быть уникальным: повторная отправка того же адреса вернёт `409`.
""",
    responses={
        201: {
            "description": "Пользователь успешно создан и сохранён в базе",
            "content": {"application/json": {"example": USER_CREATED_EXAMPLE}},
        },
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def create_user(
    payload: Annotated[UserCreate, Body(openapi_examples=CREATE_USER_EXAMPLES)],
    db: DbSession,
) -> User:
    """Создаёт пользователя; email должен быть уникальным."""
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        ) from None
    db.refresh(user)
    return user


@router.get(
    "/me",
    response_model=UserRead,
    summary="Текущий пользователь",
    description="""Возвращает пользователя, которому принадлежит access-токен.

Ручка защищена: нужен заголовок `Authorization: Bearer <token>`, который
выдаёт `POST /auth/login`. В Swagger UI токен подставляется после нажатия
**Authorize**.

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
    summary="Получить пользователя по id",
    description="""Возвращает пользователя из PostgreSQL по идентификатору.

**Пример запроса:**

```bash
curl http://localhost:8000/users/1
```

Если пользователя с таким id нет — вернётся `404`.
""",
    responses={
        200: {
            "description": "Пользователь найден",
            "content": {"application/json": {"example": USER_CREATED_EXAMPLE}},
        },
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
) -> User:
    """Возвращает пользователя или 404, если он не найден."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return user
