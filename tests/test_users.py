"""Тесты создания и чтения пользователей."""

from __future__ import annotations

from fastapi.testclient import TestClient

_USER = {"email": "ivan.petrov@example.com", "full_name": "Иван Петров"}


def test_create_user_returns_created_user(client: TestClient) -> None:
    """POST /users создаёт пользователя и возвращает 201."""
    response = client.post("/users", json=_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["email"] == _USER["email"]
    assert body["full_name"] == _USER["full_name"]
    assert "created_at" in body


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
    response = client.post("/users", json={"email": "not-an-email", "full_name": "Иван"})

    assert response.status_code == 422


def test_empty_full_name_returns_422(client: TestClient) -> None:
    """Пустое имя отклоняется валидацией."""
    response = client.post("/users", json={"email": "a@example.com", "full_name": ""})

    assert response.status_code == 422


def test_unknown_field_returns_422(client: TestClient) -> None:
    """Лишнее поле отклоняется (extra="forbid")."""
    response = client.post("/users", json={**_USER, "is_admin": True})

    assert response.status_code == 422
