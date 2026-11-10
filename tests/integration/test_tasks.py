"""Интеграционные тесты CRUD задач, прав доступа, фильтров и пагинации."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers, create_task, get_profile


async def test_create_task_returns_defaults(async_client: AsyncClient, user_token: str) -> None:
    """Новая задача получает статус pending и приоритет medium."""
    user = await get_profile(async_client, user_token)

    response = await async_client.post(
        "/tasks", json={"title": "Разработать API"}, headers=auth_headers(user_token)
    )

    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "Разработать API"
    assert task["description"] is None
    assert task["status"] == "pending"
    assert task["priority"] == "medium"
    assert task["deadline"] is None
    assert task["user_id"] == user["id"]
    assert task["created_at"] and task["updated_at"]


async def test_create_task_with_all_fields(async_client: AsyncClient, user_token: str) -> None:
    """Все поля из запроса сохраняются и возвращаются."""
    deadline = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)

    task = await create_task(
        async_client,
        user_token,
        title="Подготовить отчёт",
        description="С графиками",
        status="in_progress",
        priority="high",
        deadline=deadline.isoformat(),
    )

    assert task["description"] == "С графиками"
    assert task["status"] == "in_progress"
    assert task["priority"] == "high"
    assert task["deadline"] is not None


async def test_get_task_by_id(async_client: AsyncClient, user_token: str) -> None:
    """Задача читается по id."""
    created = await create_task(async_client, user_token, title="Прочитать")

    response = await async_client.get(f"/tasks/{created['id']}", headers=auth_headers(user_token))

    assert response.status_code == 200, response.text
    assert response.json() == created


async def test_get_unknown_task_returns_404(async_client: AsyncClient, user_token: str) -> None:
    """Несуществующий id даёт 404."""
    response = await async_client.get("/tasks/999999", headers=auth_headers(user_token))

    assert response.status_code == 404
    assert response.json()["detail"] == "Задача не найдена"


async def test_user_cannot_read_foreign_task(
    async_client: AsyncClient, user_token: str, other_user_token: str
) -> None:
    """Чужая задача недоступна обычному пользователю."""
    foreign = await create_task(async_client, other_user_token, title="Чужая")

    response = await async_client.get(f"/tasks/{foreign['id']}", headers=auth_headers(user_token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав"


async def test_user_cannot_update_foreign_task(
    async_client: AsyncClient, user_token: str, other_user_token: str
) -> None:
    """Чужую задачу нельзя изменить."""
    foreign = await create_task(async_client, other_user_token, title="Чужая")

    response = await async_client.put(
        f"/tasks/{foreign['id']}",
        json={"title": "Взлом"},
        headers=auth_headers(user_token),
    )

    assert response.status_code == 403

    check = await async_client.get(
        f"/tasks/{foreign['id']}", headers=auth_headers(other_user_token)
    )
    assert check.json()["title"] == "Чужая"


async def test_user_cannot_delete_foreign_task(
    async_client: AsyncClient, user_token: str, other_user_token: str
) -> None:
    """Чужую задачу нельзя удалить, она остаётся у владельца."""
    foreign = await create_task(async_client, other_user_token, title="Чужая")

    response = await async_client.delete(
        f"/tasks/{foreign['id']}", headers=auth_headers(user_token)
    )

    assert response.status_code == 403

    check = await async_client.get(
        f"/tasks/{foreign['id']}", headers=auth_headers(other_user_token)
    )
    assert check.status_code == 200


async def test_update_task_changes_fields(async_client: AsyncClient, user_token: str) -> None:
    """PUT меняет только переданные поля."""
    created = await create_task(async_client, user_token, title="Старый заголовок")

    response = await async_client.put(
        f"/tasks/{created['id']}",
        json={"title": "Новый заголовок", "status": "done", "priority": "low"},
        headers=auth_headers(user_token),
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["title"] == "Новый заголовок"
    assert updated["status"] == "done"
    assert updated["priority"] == "low"
    assert updated["description"] is None


async def test_update_with_empty_title_returns_422(
    async_client: AsyncClient, user_token: str
) -> None:
    """Пустой заголовок не проходит валидацию."""
    created = await create_task(async_client, user_token)

    response = await async_client.put(
        f"/tasks/{created['id']}", json={"title": ""}, headers=auth_headers(user_token)
    )

    assert response.status_code == 422


async def test_delete_task_returns_204(async_client: AsyncClient, user_token: str) -> None:
    """DELETE отдаёт 204 без тела, после чего задача недоступна."""
    created = await create_task(async_client, user_token)

    response = await async_client.delete(
        f"/tasks/{created['id']}", headers=auth_headers(user_token)
    )

    assert response.status_code == 204
    assert response.content == b""

    check = await async_client.get(f"/tasks/{created['id']}", headers=auth_headers(user_token))
    assert check.status_code == 404


async def test_delete_unknown_task_returns_404(async_client: AsyncClient, user_token: str) -> None:
    """Удаление несуществующей задачи даёт 404."""
    response = await async_client.delete("/tasks/999999", headers=auth_headers(user_token))

    assert response.status_code == 404


async def test_list_tasks_returns_only_own_tasks(
    async_client: AsyncClient, user_token: str, other_user_token: str
) -> None:
    """Пользователь видит в списке только свои задачи."""
    user = await get_profile(async_client, user_token)
    await create_task(async_client, user_token, title="Моя 1")
    await create_task(async_client, user_token, title="Моя 2")
    await create_task(async_client, other_user_token, title="Чужая")

    response = await async_client.get("/tasks", headers=auth_headers(user_token))

    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 2
    assert {task["title"] for task in page["items"]} == {"Моя 1", "Моя 2"}
    assert {task["user_id"] for task in page["items"]} == {user["id"]}


async def test_list_tasks_filters_by_status_and_priority(
    async_client: AsyncClient, user_token: str
) -> None:
    """Фильтры status и priority комбинируются."""
    await create_task(async_client, user_token, title="Ждёт", status="pending", priority="medium")
    await create_task(async_client, user_token, title="Готово", status="done", priority="high")
    await create_task(
        async_client, user_token, title="В работе", status="in_progress", priority="high"
    )

    only_done = await async_client.get(
        "/tasks", params={"status": "done"}, headers=auth_headers(user_token)
    )
    assert [task["title"] for task in only_done.json()["items"]] == ["Готово"]
    assert only_done.json()["total"] == 1

    only_high = await async_client.get(
        "/tasks", params={"priority": "high"}, headers=auth_headers(user_token)
    )
    assert {task["title"] for task in only_high.json()["items"]} == {"Готово", "В работе"}

    both = await async_client.get(
        "/tasks",
        params={"status": "in_progress", "priority": "high"},
        headers=auth_headers(user_token),
    )
    assert [task["title"] for task in both.json()["items"]] == ["В работе"]


async def test_list_tasks_filters_by_deadline_range(
    async_client: AsyncClient, user_token: str
) -> None:
    """deadline_from / deadline_to отсекают задачи по дедлайну."""
    now = datetime.now(UTC)
    past = (now - timedelta(days=2)).replace(microsecond=0).isoformat()
    future = (now + timedelta(days=2)).replace(microsecond=0).isoformat()
    moment = now.replace(microsecond=0).isoformat()

    await create_task(async_client, user_token, title="Просроченная", deadline=past)
    await create_task(async_client, user_token, title="Будущая", deadline=future)
    await create_task(async_client, user_token, title="Без дедлайна")

    after_now = await async_client.get(
        "/tasks", params={"deadline_from": moment}, headers=auth_headers(user_token)
    )
    assert [task["title"] for task in after_now.json()["items"]] == ["Будущая"]

    before_now = await async_client.get(
        "/tasks", params={"deadline_to": moment}, headers=auth_headers(user_token)
    )
    assert [task["title"] for task in before_now.json()["items"]] == ["Просроченная"]


async def test_list_tasks_pagination(async_client: AsyncClient, user_token: str) -> None:
    """limit/offset отдают непересекающиеся страницы и общий total."""
    for index in range(3):
        await create_task(async_client, user_token, title=f"Задача {index}")

    first_page = await async_client.get(
        "/tasks", params={"limit": 2, "offset": 0}, headers=auth_headers(user_token)
    )
    body = first_page.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    second_page = await async_client.get(
        "/tasks", params={"limit": 2, "offset": 2}, headers=auth_headers(user_token)
    )
    second_body = second_page.json()
    assert second_body["total"] == 3
    assert len(second_body["items"]) == 1

    titles = {task["title"] for task in body["items"] + second_body["items"]}
    assert titles == {"Задача 0", "Задача 1", "Задача 2"}


async def test_list_tasks_returns_empty_page(async_client: AsyncClient, user_token: str) -> None:
    """Без задач список пуст, но структура страницы сохраняется."""
    response = await async_client.get("/tasks", headers=auth_headers(user_token))

    assert response.status_code == 200
    assert response.json() == {"total": 0, "limit": 20, "offset": 0, "items": []}


async def test_list_tasks_invalid_limit_returns_422(
    async_client: AsyncClient, user_token: str
) -> None:
    """limit вне диапазона 1..100 отклоняется."""
    too_small = await async_client.get(
        "/tasks", params={"limit": 0}, headers=auth_headers(user_token)
    )
    too_big = await async_client.get(
        "/tasks", params={"limit": 101}, headers=auth_headers(user_token)
    )

    assert too_small.status_code == 422
    assert too_big.status_code == 422


async def test_list_tasks_invalid_status_returns_422(
    async_client: AsyncClient, user_token: str
) -> None:
    """Неизвестный статус в фильтре отклоняется."""
    response = await async_client.get(
        "/tasks", params={"status": "archived"}, headers=auth_headers(user_token)
    )

    assert response.status_code == 422


async def test_create_task_with_empty_title_returns_422(
    async_client: AsyncClient, user_token: str
) -> None:
    """Заголовок обязателен и не может быть пустым."""
    response = await async_client.post(
        "/tasks", json={"title": ""}, headers=auth_headers(user_token)
    )

    assert response.status_code == 422


async def test_create_task_with_unknown_status_returns_422(
    async_client: AsyncClient, user_token: str
) -> None:
    """Статус вне перечисления отклоняется."""
    response = await async_client.post(
        "/tasks",
        json={"title": "Задача", "status": "archived"},
        headers=auth_headers(user_token),
    )

    assert response.status_code == 422


async def test_tasks_require_authentication(async_client: AsyncClient) -> None:
    """Без токена все ручки задач отвечают 401."""
    assert (await async_client.get("/tasks")).status_code == 401
    assert (await async_client.post("/tasks", json={"title": "Без токена"})).status_code == 401
    assert (await async_client.get("/tasks/1")).status_code == 401
    assert (await async_client.put("/tasks/1", json={"title": "Без токена"})).status_code == 401
    assert (await async_client.delete("/tasks/1")).status_code == 401


async def test_admin_sees_all_tasks(
    async_client: AsyncClient, user_token: str, admin_token: str
) -> None:
    """ADMIN видит задачи всех пользователей и открывает любую из них."""
    foreign = await create_task(async_client, user_token, title="Задача пользователя")

    listing = await async_client.get("/tasks", headers=auth_headers(admin_token))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["title"] == "Задача пользователя"

    detail = await async_client.get(f"/tasks/{foreign['id']}", headers=auth_headers(admin_token))
    assert detail.status_code == 200


async def test_admin_can_update_foreign_task(
    async_client: AsyncClient, user_token: str, admin_token: str
) -> None:
    """ADMIN может изменить чужую задачу."""
    foreign = await create_task(async_client, user_token, title="До админа")

    response = await async_client.put(
        f"/tasks/{foreign['id']}",
        json={"status": "done"},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "done"


async def test_create_task_writes_notification_log(
    async_client: AsyncClient, user_token: str, caplog: pytest.LogCaptureFixture
) -> None:
    """После создания задачи фоновая «отправка письма» пишет строку в лог."""
    with caplog.at_level(logging.INFO, logger="app.notifications"):
        await create_task(async_client, user_token, title="Уведомление о задаче")

    assert "email:" in caplog.text
    assert "Уведомление о задаче" in caplog.text
