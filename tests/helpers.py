"""Вспомогательные функции интеграционных тестов.

Здесь собраны короткие обёртки над HTTP-запросами, чтобы сами тесты читались
как сценарии: зарегистрировать пользователя, войти, создать задачу.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

DEFAULT_PASSWORD = "secret123"  # noqa: S105 — пароль используется только в тестах


def auth_headers(token: str) -> dict[str, str]:
    """Возвращает заголовок ``Authorization`` с Bearer-токеном."""
    return {"Authorization": f"Bearer {token}"}


async def register_user(
    client: AsyncClient,
    email: str,
    *,
    password: str = DEFAULT_PASSWORD,
    name: str = "Тестовый пользователь",
) -> dict[str, Any]:
    """Регистрирует пользователя через API и возвращает тело ответа."""
    response = await client.post(
        "/auth/register", json={"email": email, "password": password, "name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(client: AsyncClient, email: str, *, password: str = DEFAULT_PASSWORD) -> str:
    """Входит под пользователем и возвращает access-токен.

    Используется ``POST /auth/token`` — ручка для API-клиентов, которая отдаёт
    токен в теле ответа. Браузерная сессия живёт в HttpOnly-cookie.
    """
    response = await client.post("/auth/token", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def register_and_login(
    client: AsyncClient,
    email: str,
    *,
    password: str = DEFAULT_PASSWORD,
    name: str = "Тестовый пользователь",
) -> str:
    """Регистрирует пользователя и сразу возвращает его токен."""
    await register_user(client, email, password=password, name=name)
    return await login(client, email, password=password)


async def get_profile(client: AsyncClient, token: str) -> dict[str, Any]:
    """Возвращает профиль владельца токена."""
    response = await client.get("/auth/profile", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


async def promote_to_admin(user_id: int) -> None:
    """Назначает роль ADMIN напрямую в БД.

    Публичной ручки выдачи админских прав нет (первого администратора назначают
    SQL-запросом, см. README), поэтому тест делает то же самое через сессию.
    """
    from sqlalchemy import update

    from src.core.database import async_session_factory
    from src.models.user import User

    async with async_session_factory() as session:
        await session.execute(update(User).where(User.id == user_id).values(role="ADMIN"))
        await session.commit()


async def create_task(
    client: AsyncClient,
    token: str,
    *,
    title: str = "Тестовая задача",
    **fields: Any,
) -> dict[str, Any]:
    """Создаёт задачу от имени владельца токена и возвращает тело ответа."""
    response = await client.post(
        "/tasks", json={"title": title, **fields}, headers=auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()
