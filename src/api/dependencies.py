"""Зависимости FastAPI: сессия БД и текущий пользователь."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cookies import ACCESS_COOKIE
from src.core.database import get_session
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security import decode_access_token
from src.models.user import User, UserRole

DbSession = Annotated[AsyncSession, Depends(get_session)]

# Bearer оставлен для API-клиентов, curl и Swagger UI: SPA ходит через cookie.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Access-токен для API-клиентов. Браузер использует HttpOnly-cookie.",
)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
) -> User:
    """Достаёт пользователя из cookie сессии или заголовка ``Authorization``."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token and credentials is not None:
        token = credentials.credentials
    if not token:
        raise UnauthorizedError("Не удалось проверить токен")

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedError("Не удалось проверить токен") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Не удалось проверить токен")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> User:
    """Пропускает только администратора."""
    if current_user.role != UserRole.ADMIN.value:
        raise ForbiddenError("Недостаточно прав")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
