"""Зависимости FastAPI: текущий пользователь по JWT и RBAC."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ROLE_ADMIN, User
from app.security import decode_access_token

# ``tokenUrl`` используется Swagger UI: кнопка Authorize отправляет форму
# с логином и паролем на этот адрес.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DbSession = Annotated[Session, Depends(get_db)]
BearerToken = Annotated[str, Depends(oauth2_scheme)]


def get_current_user(token: BearerToken, db: DbSession) -> User:
    """Возвращает пользователя из ``sub`` access-токена."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить токен",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise credentials_exception from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    """Фабрика зависимостей: текущий пользователь должен иметь одну из ролей.

    Использование:

        def read_all(current_user: Annotated[User, Depends(require_roles(ROLE_ADMIN))]) -> ...

    Возвращает 403 при недостаточных правах (после успешной аутентификации).
    """

    def _require_role(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return current_user

    return _require_role


AdminUser = Annotated[User, Depends(require_roles(ROLE_ADMIN))]
