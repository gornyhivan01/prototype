"""Аутентификация по паролю: выдача JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.examples import (
    INVALID_CREDENTIALS_RESPONSE,
    TOKEN_EXAMPLE,
    VALIDATION_RESPONSE,
)
from app.models import User
from app.schemas import Token
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/login",
    response_model=Token,
    summary="Войти и получить JWT",
    description="""Проверяет email и пароль и возвращает access-токен.

**В Swagger UI:** нажмите **Authorize**, введите email в поле *username*,
пароль — в поле *password*, затем **Authorize**. Токен подставится в запросы
автоматически.

**Пример запроса:**

```bash
curl -X POST http://localhost:8000/auth/login \\
  -H 'Content-Type: application/x-www-form-urlencoded' \\
  -d 'username=ivan.petrov@example.com&password=secret123'
```

Неверный email и неверный пароль дают одинаковый ответ `401`, чтобы нельзя было
проверить существование пользователя.

**Время жизни.** Токен действует `ACCESS_TOKEN_EXPIRE_MINUTES` минут (по
умолчанию 30). Срок записан в claim `exp`; после него сервер вернёт `401`, и
нужно войти заново. Ответ содержит `expires_in` — тот же срок в секундах.
""",
    responses={
        200: {
            "description": "Токен выдан",
            "content": {"application/json": {"example": TOKEN_EXAMPLE}},
        },
        401: INVALID_CREDENTIALS_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> Token:
    """Проверяет пароль и возвращает JWT."""
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(
        access_token=create_access_token(subject=str(user.id)),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )
