"""Тесты создания и чтения пользователей."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

_USER = {
    "email": "ivan.petrov@example.com",
    "full_name": "Иван Петров",
    "password": "secret123",
}


def test_create_user_returns_created_user(client: TestClient) -> None:
    """POST /users создаёт пользователя и возвращает 201."""
    response = client.post("/users", json=_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["email"] == _USER["email"]
    assert body["full_name"] == _USER["full_name"]
    assert "created_at" in body


def test_create_user_does_not_return_password(client: TestClient) -> None:
    """Пароль и его хеш не попадают в ответ API."""
    body = client.post("/users", json=_USER).json()

    assert "password" not in body
    assert "hashed_password" not in body


def test_password_is_stored_as_argon2id_hash(client: TestClient, db_session: Session) -> None:
    """В базе лежит Argon2id-хеш, а не исходный пароль."""
    client.post("/users", json=_USER)

    user = db_session.scalar(select(User).where(User.email == _USER["email"]))

    assert user is not None
    assert user.hashed_password != _USER["password"]
    assert user.hashed_password.startswith("$argon2id$")
    assert len(user.hashed_password) <= 255


def test_same_password_produces_different_hashes(client: TestClient, db_session: Session) -> None:
    """Соль делает хеши одинаковых паролей разными."""
    client.post("/users", json={**_USER, "email": "first@example.com"})
    client.post("/users", json={**_USER, "email": "second@example.com"})

    hashes = db_session.scalars(select(User.hashed_password)).all()

    assert len(hashes) == 2
    assert hashes[0] != hashes[1]


def test_get_user_by_id(client: TestClient) -> None:
    """GET /users/{id} возвращает ранее созданного пользователя."""
    created = client.post("/users", json=_USER).json()

    response = client.get(f"/users/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_user_returns_404(client: TestClient) -> None:
    """GET /users/{id} для несуществующего id возвращает 404."""
    response = client.get("/users/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Пользователь не найден"


def test_duplicate_email_returns_409(client: TestClient) -> None:
    """Повторный email нарушает уникальность и возвращает 409."""
    assert client.post("/users", json=_USER).status_code == 201

    response = client.post("/users", json=_USER)

    assert response.status_code == 409
    assert response.json()["detail"] == "Пользователь с таким email уже существует"


def test_invalid_email_returns_422(client: TestClient) -> None:
    """Некорректный email отклоняется валидацией."""
    response = client.post(
        "/users",
        json={"email": "not-an-email", "full_name": "Иван", "password": "secret123"},
    )

    assert response.status_code == 422


def test_empty_full_name_returns_422(client: TestClient) -> None:
    """Пустое имя отклоняется валидацией."""
    response = client.post(
        "/users",
        json={"email": "a@example.com", "full_name": "", "password": "secret123"},
    )

    assert response.status_code == 422


def test_short_password_returns_422(client: TestClient) -> None:
    """Пароль короче 8 символов отклоняется валидацией."""
    response = client.post(
        "/users",
        json={"email": "a@example.com", "full_name": "Иван", "password": "short"},
    )

    assert response.status_code == 422


def test_unknown_field_returns_422(client: TestClient) -> None:
    """Лишнее поле отклоняется (extra="forbid")."""
    response = client.post("/users", json={**_USER, "is_admin": True})

    assert response.status_code == 422
