"""Интеграционные тесты журнала аудита и его интеграции с действиями."""

from __future__ import annotations

from httpx import AsyncClient

from tests.helpers import (
    DEFAULT_PASSWORD,
    auth_headers,
    create_task,
    login,
    register_user,
)


async def _read(
    client: AsyncClient, token: str, path: str = "/audit", **params: object
) -> dict[str, object]:
    """Читает страницу журнала и возвращает тело ответа."""
    response = await client.get(path, params=params, headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


async def test_audit_endpoints_require_token(async_client: AsyncClient) -> None:
    """Без токена журнал недоступен."""
    assert (await async_client.get("/audit")).status_code == 401
    assert (await async_client.get("/audit/me")).status_code == 401


async def test_register_and_login_are_logged(async_client: AsyncClient) -> None:
    """Создание учётки и успешный вход попадают в «мои события»."""
    user = await register_user(async_client, "audit@example.com", name="Аудит")
    token = await login(async_client, "audit@example.com")

    page = await _read(async_client, token, "/audit/me")

    actions = [item["action"] for item in page["items"]]
    assert "user.created" in actions
    assert "auth.login.success" in actions

    created = next(item for item in page["items"] if item["action"] == "user.created")
    assert created["target_user_id"] == user["id"]
    assert created["email"] == "audit@example.com"
    # Пароль и хеш в журнал не попадают.
    assert "password" not in str(created)


async def test_failed_login_is_logged(async_client: AsyncClient, user_token: str) -> None:
    """Неудачная попытка входа сохраняется с причиной."""
    response = await async_client.post(
        "/auth/login", json={"email": "user@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401

    page = await _read(async_client, user_token, "/audit/me")

    failed = [item for item in page["items"] if item["action"] == "auth.login.failed"]
    assert failed
    assert failed[0]["details"] == {"reason": "invalid_password"}
    assert failed[0]["actor_id"] is None
    assert failed[0]["email"] == "user@example.com"


async def test_full_log_is_admin_only(async_client: AsyncClient, user_token: str) -> None:
    """Обычный пользователь не видит журнал целиком."""
    response = await async_client.get("/audit", headers=auth_headers(user_token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав"


async def test_admin_sees_events_of_all_users(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """Администратор видит события других пользователей."""
    page = await _read(async_client, admin_token)

    emails = {item["email"] for item in page["items"] if item["email"]}
    assert {"admin@example.com", "user@example.com"} <= emails


async def test_my_events_do_not_leak_others(
    async_client: AsyncClient, user_token: str, other_user_token: str
) -> None:
    """«Мои события» не содержат чужих записей."""
    page = await _read(async_client, user_token, "/audit/me")

    emails = {item["email"] for item in page["items"] if item["email"]}
    assert emails <= {"user@example.com"}


async def test_action_filter_and_pagination(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """Фильтр по действию и limit/offset работают."""
    await register_user(async_client, "extra@example.com")

    page = await _read(async_client, admin_token, action="user.created")
    assert page["total"] >= 3
    assert all(item["action"] == "user.created" for item in page["items"])

    first = await _read(async_client, admin_token, action="user.created", limit=1, offset=0)
    assert first["limit"] == 1
    assert first["offset"] == 0
    assert len(first["items"]) == 1

    second = await _read(async_client, admin_token, action="user.created", limit=1, offset=1)
    assert len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]


async def test_email_filter(async_client: AsyncClient, admin_token: str) -> None:
    """Фильтр по email ищет подстроку без учёта регистра."""
    await register_user(async_client, "filtered@example.com")

    page = await _read(async_client, admin_token, email="FILTERED@")

    assert page["total"] >= 1
    assert all("filtered@" in (item["email"] or "") for item in page["items"])


async def test_task_events_are_logged(async_client: AsyncClient, user_token: str) -> None:
    """Создание, изменение и удаление задачи попадают в аудит."""
    task = await create_task(async_client, user_token, title="Задача для аудита")
    await async_client.patch(
        f"/tasks/{task['id']}", json={"status": "done"}, headers=auth_headers(user_token)
    )
    await async_client.delete(f"/tasks/{task['id']}", headers=auth_headers(user_token))

    page = await _read(async_client, user_token, "/audit/me")

    actions = {item["action"] for item in page["items"]}
    assert {"task.created", "task.updated", "task.deleted"} <= actions

    created = next(item for item in page["items"] if item["action"] == "task.created")
    assert created["details"]["task_id"] == task["id"]
    status_changed = next(item for item in page["items"] if item["action"] == "task.updated")
    assert status_changed["details"]["fields"] == ["status"]


async def test_user_deletion_is_logged_and_survives_target(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Удаление пользователя пишется в журнал; FK обнуляет target_user_id."""
    created = await async_client.post(
        "/admin/users",
        json={
            "email": "victim-audit@example.com",
            "password": DEFAULT_PASSWORD,
            "name": "Удаляемый",
        },
        headers=auth_headers(admin_token),
    )
    assert created.status_code == 201, created.text
    victim = created.json()

    response = await async_client.delete(
        f"/admin/users/{victim['id']}", headers=auth_headers(admin_token)
    )
    assert response.status_code == 204

    page = await _read(async_client, admin_token, action="user.deleted")

    deleted = next(item for item in page["items"] if item["email"] == "victim-audit@example.com")
    assert deleted["actor_id"] is not None
    # Пользователя больше нет — внешний ключ обнулил ссылку, но запись осталась.
    assert deleted["target_user_id"] is None
    assert deleted["details"] == {"archived_tasks": 0}


async def test_role_change_is_logged(async_client: AsyncClient, admin_token: str) -> None:
    """Смена роли фиксируется с прежним и новым значением."""
    created = await async_client.post(
        "/admin/users",
        json={
            "email": "promoted@example.com",
            "password": DEFAULT_PASSWORD,
            "name": "Повышаемый",
        },
        headers=auth_headers(admin_token),
    )
    user_id = created.json()["id"]

    response = await async_client.patch(
        f"/admin/users/{user_id}/role",
        json={"role": "ADMIN"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200

    page = await _read(async_client, admin_token, action="user.role_changed")

    event = next(item for item in page["items"] if item["target_user_id"] == user_id)
    assert event["details"] == {"from": "USER", "to": "ADMIN"}
