"""Тесты API журнала аудита: полный доступ админа и «свои» события пользователя."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_USER: dict[str, Any] = {
    "email": "audit.target@example.com",
    "full_name": "Целевой Пользователь",
    "password": "secret123",
    "role": "user",
}


def _create_user(
    client: TestClient, headers: dict[str, str], email: str = _USER["email"]
) -> dict[str, Any]:
    payload = {**_USER, "email": email}
    response = client.post("/users", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_sees_full_audit_log(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Админ видит события всех пользователей, а не только свои."""
    created = _create_user(client, admin_headers)
    _login_headers(client, _USER["email"], _USER["password"])

    response = client.get("/audit", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 3  # вход админа, создание, вход пользователя
    actions = {(item["action"], item["email"]) for item in body["items"]}
    assert ("user.created", _USER["email"]) in actions
    assert ("auth.login.success", _USER["email"]) in actions
    ids = [item["id"] for item in body["items"]]
    assert ids == sorted(ids, reverse=True)  # новые первыми
    assert created["id"] in {item["target_user_id"] for item in body["items"]}


def test_user_cannot_read_full_audit_log(client: TestClient, user_headers: dict[str, str]) -> None:
    """Обычному пользователю полный журнал запрещён."""
    response = client.get("/audit", headers=user_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав"


def test_user_sees_only_own_events(
    client: TestClient,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    """В /audit/me нет чужих событий — ни админских, ни других пользователей."""
    _create_user(client, admin_headers)  # событие user.created о другом человеке

    response = client.get("/audit/me", headers=user_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    me = client.get("/users/me", headers=user_headers).json()
    for item in body["items"]:
        assert (
            item["actor_id"] == me["id"]
            or item["target_user_id"] == me["id"]
            or (item["actor_id"] is None and item["email"] == me["email"])
        )
    emails = {item["email"] for item in body["items"]}
    assert "admin@example.com" not in emails


def test_user_sees_events_about_own_account(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Создание учётки админом и вход попадают в «мои события»."""
    created = _create_user(client, admin_headers)
    headers = _login_headers(client, _USER["email"], _USER["password"])

    body = client.get("/audit/me", headers=headers).json()

    targets = {item["target_user_id"] for item in body["items"]}
    assert created["id"] in targets
    actions = {item["action"] for item in body["items"]}
    assert "user.created" in actions
    assert "auth.login.success" in actions


def test_failed_login_is_visible_in_own_events(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """Неудачная попытка входа с email пользователя видна ему в /audit/me."""
    client.post(
        "/auth/login",
        data={"username": "user@example.com", "password": "wrong-password"},
    )

    body = client.get("/audit/me", headers=user_headers).json()

    failed = [
        item
        for item in body["items"]
        if item["action"] == "auth.login.failed" and item["email"] == "user@example.com"
    ]
    assert failed, body


def test_admin_can_filter_by_action(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Фильтр action оставляет только нужные события."""
    _create_user(client, admin_headers)

    response = client.get("/audit", params={"action": "user.created"}, headers=admin_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert {item["action"] for item in items} == {"user.created"}


def test_admin_can_filter_by_email_substring(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Фильтр email ищет подстроку без учёта регистра."""
    _create_user(client, admin_headers)

    response = client.get("/audit", params={"email": "AUDIT.TARGET"}, headers=admin_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all("audit.target" in item["email"] for item in items)


def test_audit_pagination(client: TestClient, admin_headers: dict[str, str]) -> None:
    """limit/offset листают журнал без пересечений."""
    for index in range(3):
        _create_user(client, admin_headers, f"audit.page{index}@example.com")

    first = client.get("/audit", params={"limit": 2, "offset": 0}, headers=admin_headers).json()
    second = client.get("/audit", params={"limit": 2, "offset": 2}, headers=admin_headers).json()

    assert len(first["items"]) == 2
    assert first["total"] == second["total"] >= 3
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_audit_limit_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    """limit больше 200 (или 0) — ошибка валидации."""
    assert client.get("/audit", params={"limit": 0}, headers=admin_headers).status_code == 422
    assert client.get("/audit", params={"limit": 500}, headers=admin_headers).status_code == 422


def test_audit_requires_token(client: TestClient) -> None:
    """Без токена обе ручки возвращают 401."""
    assert client.get("/audit").status_code == 401
    assert client.get("/audit/me").status_code == 401
