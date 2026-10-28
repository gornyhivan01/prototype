"""Тесты создания и чтения пользователей (RBAC: создание/список — только admin)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import AuditAction
from app.models import AuditLog, User

_USER = {
    "email": "ivan.petrov@example.com",
    "full_name": "Иван Петров",
    "password": "secret123",
}


def test_anon_cannot_create_user(client: TestClient) -> None:
    """Аноним не может создать пользователя — 401."""
    response = client.post("/users", json=_USER)
    assert response.status_code == 401


def test_regular_user_cannot_create_user(client: TestClient, user_headers: dict) -> None:
    """Обычный пользователь не может создавать пользователей — 403."""
    response = client.post("/users", json=_USER, headers=user_headers)
    assert response.status_code == 403


def test_admin_creates_user_returns_created_user(client: TestClient, admin_headers: dict) -> None:
    """POST /users от имени админа создаёт пользователя и возвращает 201."""
    response = client.post("/users", json=_USER, headers=admin_headers)

    assert response.status_code == 201
    body = response.json()
    assert "id" in body and isinstance(body["id"], int)
    assert body["email"] == _USER["email"]
    assert body["full_name"] == _USER["full_name"]
    assert body["role"] == "user"
    assert "created_at" in body


def test_admin_can_create_user_with_role_admin(client: TestClient, admin_headers: dict) -> None:
    """Админ может создать другого админа, задав role='admin'."""
    response = client.post("/users", json={**_USER, "role": "admin"}, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


def test_create_user_does_not_return_password(client: TestClient, admin_headers: dict) -> None:
    """Пароль и его хеш не попадают в ответ API."""
    body = client.post("/users", json=_USER, headers=admin_headers).json()

    assert "password" not in body
    assert "hashed_password" not in body


def test_password_is_stored_as_argon2id_hash(
    client: TestClient, admin_headers: dict, db_session: Session
) -> None:
    """В базе лежит Argon2id-хеш, а не исходный пароль."""
    client.post("/users", json=_USER, headers=admin_headers)

    user = db_session.scalar(select(User).where(User.email == _USER["email"]))

    assert user is not None
    assert user.hashed_password != _USER["password"]
    assert user.hashed_password.startswith("$argon2id$")
    assert len(user.hashed_password) <= 255


def test_same_password_produces_different_hashes(
    client: TestClient, admin_headers: dict, db_session: Session
) -> None:
    """Соль делает хеши одинаковых паролей разными."""
    client.post("/users", json={**_USER, "email": "first@example.com"}, headers=admin_headers)
    client.post("/users", json={**_USER, "email": "second@example.com"}, headers=admin_headers)

    hashes = db_session.scalars(
        select(User.hashed_password).where(
            User.email.in_(("first@example.com", "second@example.com"))
        )
    ).all()

    assert len(hashes) == 2
    assert hashes[0] != hashes[1]


def test_admin_lists_users(client: TestClient, admin_headers: dict) -> None:
    """GET /users доступен админу и возвращает всех."""
    client.post("/users", json=_USER, headers=admin_headers)
    client.post("/users", json={**_USER, "email": "second@example.com"}, headers=admin_headers)

    response = client.get("/users", headers=admin_headers)

    assert response.status_code == 200
    emails = {user["email"] for user in response.json()}
    assert {"ivan.petrov@example.com", "second@example.com"} <= emails


def test_anon_cannot_list_users(client: TestClient) -> None:
    """Аноним не может получить список пользователей — 401."""
    assert client.get("/users").status_code == 401


def test_regular_user_cannot_list_users(client: TestClient, user_headers: dict) -> None:
    """Обычный пользователь не может получить список — 403."""
    assert client.get("/users", headers=user_headers).status_code == 403


def test_get_user_by_id_as_admin(client: TestClient, admin_headers: dict) -> None:
    """Админ может получить любого пользователя по id."""
    created = client.post("/users", json=_USER, headers=admin_headers).json()

    response = client.get(f"/users/{created['id']}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == created


def test_user_can_get_own_profile_by_id(client: TestClient, user_headers: dict) -> None:
    """Пользователь может получить свой собственный профиль по id."""
    me = client.get("/users/me", headers=user_headers).json()
    response = client.get(f"/users/{me['id']}", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


def test_user_gets_403_for_foreign_profile(
    client: TestClient, admin_headers: dict, user_headers: dict
) -> None:
    """Чужой профиль у обычного пользователя — 403."""
    admin_id = client.get("/users/me", headers=admin_headers).json()["id"]
    response = client.get(f"/users/{admin_id}", headers=user_headers)

    assert response.status_code == 403


def test_anon_cannot_get_user_by_id(client: TestClient) -> None:
    """Аноним не может читать чужие профили — 401."""
    assert client.get("/users/1").status_code == 401


def test_get_unknown_user_returns_404(client: TestClient, admin_headers: dict) -> None:
    """GET /users/{id} для несуществующего id возвращает 404."""
    response = client.get("/users/999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Пользователь не найден"


def test_duplicate_email_returns_409(client: TestClient, admin_headers: dict) -> None:
    """Повторный email нарушает уникальность и возвращает 409."""
    assert client.post("/users", json=_USER, headers=admin_headers).status_code == 201

    response = client.post("/users", json=_USER, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Пользователь с таким email уже существует"


def test_invalid_email_returns_422(client: TestClient, admin_headers: dict) -> None:
    """Некорректный email отклоняется валидацией."""
    response = client.post(
        "/users",
        json={"email": "not-an-email", "full_name": "Иван", "password": "secret123"},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_empty_full_name_returns_422(client: TestClient, admin_headers: dict) -> None:
    """Пустое имя отклоняется валидацией."""
    response = client.post(
        "/users",
        json={"email": "a@example.com", "full_name": "", "password": "secret123"},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_short_password_returns_422(client: TestClient, admin_headers: dict) -> None:
    """Пароль короче 8 символов отклоняется валидацией."""
    response = client.post(
        "/users",
        json={"email": "a@example.com", "full_name": "Иван", "password": "short"},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_bad_role_returns_422(client: TestClient, admin_headers: dict) -> None:
    """Неизвестная роль отклоняется валидацией."""
    response = client.post("/users", json={**_USER, "role": "root"}, headers=admin_headers)

    assert response.status_code == 422


def test_unknown_field_returns_422(client: TestClient, admin_headers: dict) -> None:
    """Лишнее поле отклоняется (extra="forbid")."""
    response = client.post("/users", json={**_USER, "is_admin": True}, headers=admin_headers)

    assert response.status_code == 422


# --- Удаление пользователей (только admin) ---


def test_admin_deletes_user(client: TestClient, admin_headers: dict, db_session: Session) -> None:
    """Админ удаляет пользователя: 204, запись пропадает из БД, аудит остаётся."""
    created = client.post("/users", json=_USER, headers=admin_headers).json()
    admin_id = client.get("/users/me", headers=admin_headers).json()["id"]

    response = client.delete(f"/users/{created['id']}", headers=admin_headers)

    assert response.status_code == 204
    assert db_session.scalar(select(User).where(User.email == _USER["email"])) is None
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == AuditAction.USER_DELETED))
    assert entry is not None
    assert entry.actor_id == admin_id
    assert entry.email == _USER["email"]


def test_deleted_user_cannot_login(client: TestClient, admin_headers: dict) -> None:
    """После удаления вход по паролю невозможен."""
    created = client.post("/users", json=_USER, headers=admin_headers).json()
    assert client.delete(f"/users/{created['id']}", headers=admin_headers).status_code == 204

    response = client.post(
        "/auth/login",
        data={"username": _USER["email"], "password": _USER["password"]},
    )
    assert response.status_code == 401


def test_anon_cannot_delete_user(client: TestClient) -> None:
    """Аноним не может удалять пользователей — 401."""
    assert client.delete("/users/1").status_code == 401


def test_regular_user_cannot_delete_user(
    client: TestClient, admin_headers: dict, user_headers: dict
) -> None:
    """Обычный пользователь не может удалять — 403."""
    created = client.post("/users", json=_USER, headers=admin_headers).json()

    response = client.delete(f"/users/{created['id']}", headers=user_headers)

    assert response.status_code == 403


def test_admin_cannot_delete_own_account(client: TestClient, admin_headers: dict) -> None:
    """Админ не может удалить сам себя — 400."""
    admin_id = client.get("/users/me", headers=admin_headers).json()["id"]

    response = client.delete(f"/users/{admin_id}", headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Нельзя удалить собственную учётку"


def test_delete_unknown_user_returns_404(client: TestClient, admin_headers: dict) -> None:
    """Удаление несуществующего пользователя — 404."""
    response = client.delete("/users/999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Пользователь не найден"
