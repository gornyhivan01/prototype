"""Интеграционные тесты админских ручек и RBAC."""

from __future__ import annotations

from httpx import AsyncClient

from tests.helpers import (
    DEFAULT_PASSWORD,
    auth_headers,
    create_task,
    login,
    register_user,
)


async def test_admin_users_requires_token(async_client: AsyncClient) -> None:
    """Без токена админская ручка недоступна."""
    response = await async_client.get("/admin/users")

    assert response.status_code == 401


async def test_admin_users_forbidden_for_user(async_client: AsyncClient, user_token: str) -> None:
    """Обычный пользователь получает 403."""
    response = await async_client.get("/admin/users", headers=auth_headers(user_token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав"


async def test_admin_users_returns_page(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """ADMIN видит список пользователей с пагинацией."""
    await register_user(async_client, "third@example.com", name="Третий")

    response = await async_client.get("/admin/users", headers=auth_headers(admin_token))

    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 3
    assert page["limit"] == 20
    assert page["offset"] == 0
    assert {user["email"] for user in page["items"]} == {
        "admin@example.com",
        "user@example.com",
        "third@example.com",
    }
    assert all("hashed_password" not in user for user in page["items"])


async def test_admin_users_pagination(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """limit/offset работают и в списке пользователей."""
    response = await async_client.get(
        "/admin/users", params={"limit": 1, "offset": 1}, headers=auth_headers(admin_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1


async def test_change_role_promotes_user(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """ADMIN повышает пользователя до ADMIN, и тому открываются админ-ручки."""
    profile = await async_client.get("/auth/profile", headers=auth_headers(user_token))
    user_id = profile.json()["id"]

    response = await async_client.put(
        f"/admin/users/{user_id}/role",
        json={"role": "ADMIN"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "ADMIN"

    promoted = await async_client.get("/admin/users", headers=auth_headers(user_token))
    assert promoted.status_code == 200

    updated_profile = await async_client.get("/auth/profile", headers=auth_headers(user_token))
    assert updated_profile.json()["role"] == "ADMIN"


async def test_change_role_back_to_user(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """Понижение роли сразу отзывает доступ к админским ручкам."""
    profile = await async_client.get("/auth/profile", headers=auth_headers(user_token))
    user_id = profile.json()["id"]

    await async_client.put(
        f"/admin/users/{user_id}/role",
        json={"role": "ADMIN"},
        headers=auth_headers(admin_token),
    )
    response = await async_client.put(
        f"/admin/users/{user_id}/role",
        json={"role": "USER"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "USER"

    forbidden = await async_client.get("/admin/users", headers=auth_headers(user_token))
    assert forbidden.status_code == 403


async def test_change_role_is_forbidden_for_user(
    async_client: AsyncClient, user_token: str
) -> None:
    """Обычный пользователь не может менять роли."""
    response = await async_client.put(
        "/admin/users/1/role", json={"role": "ADMIN"}, headers=auth_headers(user_token)
    )

    assert response.status_code == 403


async def test_change_role_unknown_user_returns_404(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Несуществующий пользователь даёт 404."""
    response = await async_client.put(
        "/admin/users/999999/role",
        json={"role": "ADMIN"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Пользователь не найден"


async def test_change_role_invalid_role_returns_422(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Роль вне перечисления отклоняется."""
    response = await async_client.put(
        "/admin/users/1/role",
        json={"role": "SUPERUSER"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 422


# --- создание пользователя администратором ---


async def test_admin_creates_user_with_requested_role(
    async_client: AsyncClient, admin_token: str
) -> None:
    """ADMIN создаёт пользователя сразу с нужной ролью."""
    response = await async_client.post(
        "/admin/users",
        json={
            "email": "created@example.com",
            "password": DEFAULT_PASSWORD,
            "name": "Созданный",
            "role": "ADMIN",
        },
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "created@example.com"
    assert body["role"] == "ADMIN"
    assert "hashed_password" not in body

    # Пароль работает: новый администратор может войти и открыть админку.
    token = await login(async_client, "created@example.com")
    profile = await async_client.get("/auth/profile", headers=auth_headers(token))
    assert profile.json()["role"] == "ADMIN"
    assert (await async_client.get("/admin/users", headers=auth_headers(token))).status_code == 200


async def test_admin_creates_user_with_default_role(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Без поля role создаётся обычный USER."""
    response = await async_client.post(
        "/admin/users",
        json={"email": "plain@example.com", "password": DEFAULT_PASSWORD, "name": "Обычный"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "USER"


async def test_admin_create_duplicate_email_returns_409(
    async_client: AsyncClient, admin_token: str, user_token: str
) -> None:
    """Email занят — 409, даже если регистрация была обычной."""
    response = await async_client.post(
        "/admin/users",
        json={"email": "user@example.com", "password": DEFAULT_PASSWORD, "name": "Дубль"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 409
    assert "уже существует" in response.json()["detail"]


async def test_admin_create_user_forbidden_for_user(
    async_client: AsyncClient, user_token: str
) -> None:
    """Обычный пользователь не может создавать учётки."""
    response = await async_client.post(
        "/admin/users",
        json={"email": "hack@example.com", "password": DEFAULT_PASSWORD, "name": "Хакер"},
        headers=auth_headers(user_token),
    )

    assert response.status_code == 403


async def test_admin_create_user_requires_token(async_client: AsyncClient) -> None:
    """Без токена создание недоступно."""
    response = await async_client.post(
        "/admin/users",
        json={"email": "anon@example.com", "password": DEFAULT_PASSWORD, "name": "Аноним"},
    )

    assert response.status_code == 401


async def test_admin_create_user_short_password_returns_422(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Пароль короче 8 символов отклоняется."""
    response = await async_client.post(
        "/admin/users",
        json={"email": "short2@example.com", "password": "12345", "name": "Короткий"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 422


# --- удаление пользователя и архив задач ---


async def _create_user(
    client: AsyncClient, admin_token: str, email: str, *, role: str = "USER"
) -> dict[str, object]:
    """Создаёт пользователя через админскую ручку и возвращает тело ответа."""
    response = await client.post(
        "/admin/users",
        json={"email": email, "password": DEFAULT_PASSWORD, "name": "Удаляемый", "role": role},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_admin_deletes_user_and_archives_tasks(
    async_client: AsyncClient, admin_token: str
) -> None:
    """При удалении пользователя его задачи уходят в архив, а не исчезают."""
    victim = await _create_user(async_client, admin_token, "victim@example.com")
    victim_token = await login(async_client, "victim@example.com")
    first = await create_task(async_client, victim_token, title="Задача 1")
    await create_task(async_client, victim_token, title="Задача 2", status="done")

    response = await async_client.delete(
        f"/admin/users/{victim['id']}", headers=auth_headers(admin_token)
    )

    assert response.status_code == 204
    assert response.content == b""

    # Пользователь исчез из списка и не может войти.
    users = await async_client.get("/admin/users", headers=auth_headers(admin_token))
    assert victim["email"] not in {user["email"] for user in users.json()["items"]}
    relogin = await async_client.post(
        "/auth/login", json={"email": "victim@example.com", "password": DEFAULT_PASSWORD}
    )
    assert relogin.status_code == 401

    # В обычном списке задач архива нет — даже у администратора.
    active = await async_client.get("/tasks", headers=auth_headers(admin_token))
    assert active.status_code == 200
    assert active.json()["total"] == 0

    # Архив виден администратору отдельным запросом.
    archived = await async_client.get(
        "/tasks", params={"archived": "true"}, headers=auth_headers(admin_token)
    )

    assert archived.status_code == 200, archived.text
    page = archived.json()
    assert page["total"] == 2
    titles = {task["title"] for task in page["items"]}
    assert titles == {"Задача 1", "Задача 2"}

    by_title = {task["title"]: task for task in page["items"]}
    kept = by_title["Задача 1"]
    assert kept["id"] == first["id"]
    assert kept["archived_at"] is not None
    assert kept["archived_owner_email"] == "victim@example.com"
    assert kept["user_id"] is None
    assert kept["status"] == "pending"
    assert by_title["Задача 2"]["status"] == "done"


async def test_admin_delete_user_without_tasks(async_client: AsyncClient, admin_token: str) -> None:
    """Удаление пользователя без задач ничего не архивирует."""
    victim = await _create_user(async_client, admin_token, "empty@example.com")

    response = await async_client.delete(
        f"/admin/users/{victim['id']}", headers=auth_headers(admin_token)
    )

    assert response.status_code == 204
    archived = await async_client.get(
        "/tasks", params={"archived": "true"}, headers=auth_headers(admin_token)
    )
    assert archived.json()["total"] == 0


async def test_admin_cannot_delete_self(async_client: AsyncClient, admin_token: str) -> None:
    """Удалить собственную учётную запись нельзя."""
    profile = await async_client.get("/auth/profile", headers=auth_headers(admin_token))
    admin_id = profile.json()["id"]

    response = await async_client.delete(
        f"/admin/users/{admin_id}", headers=auth_headers(admin_token)
    )

    assert response.status_code == 400
    assert "собственную" in response.json()["detail"]

    # Администратор остался на месте.
    users = await async_client.get("/admin/users", headers=auth_headers(admin_token))
    assert users.json()["total"] == 1


async def test_admin_delete_other_admin_is_allowed(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Другого администратора удалить можно: текущий остаётся."""
    second = await _create_user(async_client, admin_token, "second@example.com", role="ADMIN")

    response = await async_client.delete(
        f"/admin/users/{second['id']}", headers=auth_headers(admin_token)
    )

    assert response.status_code == 204


async def test_admin_delete_unknown_user_returns_404(
    async_client: AsyncClient, admin_token: str
) -> None:
    """Несуществующий пользователь даёт 404."""
    response = await async_client.delete("/admin/users/999999", headers=auth_headers(admin_token))

    assert response.status_code == 404
    assert response.json()["detail"] == "Пользователь не найден"


async def test_admin_delete_forbidden_for_user(
    async_client: AsyncClient, user_token: str, other_user_token: str
) -> None:
    """Обычный пользователь не может удалять учётки."""
    profile = await async_client.get("/auth/profile", headers=auth_headers(other_user_token))

    response = await async_client.delete(
        f"/admin/users/{profile.json()['id']}", headers=auth_headers(user_token)
    )

    assert response.status_code == 403


async def test_admin_delete_requires_token(async_client: AsyncClient) -> None:
    """Без токена удаление недоступно."""
    assert (await async_client.delete("/admin/users/1")).status_code == 401


async def test_archive_forbidden_for_regular_user(
    async_client: AsyncClient, user_token: str
) -> None:
    """Архив задач доступен только администратору."""
    response = await async_client.get(
        "/tasks", params={"archived": "true"}, headers=auth_headers(user_token)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав"
