"""Админские маршруты: пользователи, роли и удаление."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from src.api.dependencies import AdminUser, DbSession
from src.api.schemas.user import RoleUpdate, UserCreate, UserPage, UserRead
from src.core.audit import client_ip
from src.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=UserPage, summary="Список пользователей")
async def list_users(
    admin: AdminUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPage:
    """Выдаёт всех пользователей."""
    users, total = await UserService(session).list_users(limit=limit, offset=offset)
    return UserPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[UserRead.model_validate(user) for user in users],
    )


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя",
)
async def create_user(
    payload: UserCreate, admin: AdminUser, session: DbSession, request: Request
) -> UserRead:
    """Создаёт пользователя с любой ролью; доступно только ADMIN."""
    user = await UserService(session).create_user(
        email=payload.email,
        password=payload.password,
        name=payload.name,
        role=payload.role,
        actor=admin,
        ip_address=client_ip(request),
    )
    return UserRead.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Удалить пользователя",
)
async def delete_user(
    user_id: int, admin: AdminUser, session: DbSession, request: Request
) -> Response:
    """Удаляет пользователя; его задачи остаются в архиве."""
    await UserService(session).delete_user(
        admin=admin, user_id=user_id, ip_address=client_ip(request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/users/{user_id}/role", response_model=UserRead, summary="Сменить роль")
async def change_role(
    user_id: int,
    payload: RoleUpdate,
    admin: AdminUser,
    session: DbSession,
    request: Request,
) -> UserRead:
    """Меняет роль пользователя; доступно только ADMIN."""
    user = await UserService(session).change_role(
        user_id=user_id,
        role=payload.role,
        actor=admin,
        ip_address=client_ip(request),
    )
    return UserRead.model_validate(user)
