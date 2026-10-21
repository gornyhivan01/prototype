"""Тесты аутентификации по паролю и защиты ручек JWT."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import User

_USER: dict[str, Any] = {
    "email": "ivan.petrov@example.com",
    "full_name": "Иван Петров",
    "password": "secret123",
}


@pytest.fixture
def user(client: TestClient) -> dict[str, Any]:
    """Создаёт пользователя и возвращает тело ответа."""
    response = client.post("/users", json=_USER)
    assert response.status_code == 201
    return response.json()


def _encode(payload: dict[str, Any]) -> str:
    """Подписывает произвольный payload тем же ключом, что и приложение."""
    settings = get_settings()
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _token_for(user_id: str | None, *, minutes: int = 30) -> str:
    """Выпускает корректный токен с заданным сроком действия."""
    now = datetime.now(timezone.utc)
    return _encode({"sub": user_id, "iat": now, "exp": now + timedelta(minutes=minutes)})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- POST /auth/login ---


def test_login_returns_bearer_token(client: TestClient, user: dict[str, Any]) -> None:
    """Верный пароль даёт access-токен с идентификатором и сроком жизни."""
    response = client.post(
        "/auth/login",
        data={"username": _USER["email"], "password": _USER["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"  # noqa: S105 — имя поля по стандарту OAuth2
    expected_lifetime = get_settings().access_token_expire_minutes * 60
    assert body["expires_in"] == expected_lifetime

    payload = jwt.decode(
        body["access_token"],
        get_settings().secret_key,
        algorithms=[get_settings().jwt_algorithm],
    )
    assert payload["sub"] == str(user["id"])
    assert payload["exp"] - payload["iat"] == expected_lifetime


def test_token_lifetime_must_be_positive() -> None:
    """Нулевой или отрицательный срок жизни токена запрещён настройками."""
    with pytest.raises(ValidationError):
        Settings(access_token_expire_minutes=0)


def test_login_with_wrong_password_returns_401(client: TestClient, user: dict[str, Any]) -> None:
    """Неверный пароль не даёт токен."""
    response = client.post(
        "/auth/login",
        data={"username": _USER["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный email или пароль"


def test_login_with_unknown_email_returns_401(client: TestClient) -> None:
    """Несуществующий email даёт тот же ответ, что и неверный пароль."""
    response = client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": _USER["password"]},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный email или пароль"


def test_login_with_corrupted_hash_returns_401(
    client: TestClient, user: dict[str, Any], db_session: Session
) -> None:
    """Пустой хеш (например, после миграции старой строки) не роняет сервис."""
    stored = db_session.get(User, user["id"])
    assert stored is not None
    stored.hashed_password = ""
    db_session.commit()

    response = client.post(
        "/auth/login",
        data={"username": _USER["email"], "password": _USER["password"]},
    )

    assert response.status_code == 401


def test_login_without_password_returns_422(client: TestClient) -> None:
    """Форма без пароля отклоняется валидацией."""
    response = client.post("/auth/login", data={"username": _USER["email"]})

    assert response.status_code == 422


# --- GET /users/me ---


def test_me_returns_current_user(client: TestClient, user: dict[str, Any]) -> None:
    """С валидным токеном ручка возвращает владельца токена."""
    response = client.get("/users/me", headers=_auth(_token_for(str(user["id"]))))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user["id"]
    assert body["email"] == user["email"]
    assert "hashed_password" not in body


def test_me_without_token_returns_401(client: TestClient) -> None:
    """Без заголовка Authorization ручка недоступна."""
    response = client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_with_invalid_token_returns_401(client: TestClient) -> None:
    """Строка, не являющаяся JWT, отклоняется."""
    response = client.get("/users/me", headers=_auth("not-a-jwt"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Не удалось проверить токен"


def test_me_with_expired_token_returns_401(client: TestClient, user: dict[str, Any]) -> None:
    """Просроченный токен отклоняется."""
    response = client.get("/users/me", headers=_auth(_token_for(str(user["id"]), minutes=-1)))

    assert response.status_code == 401


def test_me_with_unknown_user_returns_401(client: TestClient) -> None:
    """Токен с несуществующим sub не даёт доступа."""
    response = client.get("/users/me", headers=_auth(_token_for("999")))

    assert response.status_code == 401


def test_me_with_malformed_subject_returns_401(client: TestClient) -> None:
    """Нечисловой sub не превращается в id пользователя."""
    response = client.get("/users/me", headers=_auth(_token_for("abc")))

    assert response.status_code == 401


def test_me_with_null_subject_returns_401(client: TestClient) -> None:
    """Пустой sub отклоняется."""
    response = client.get("/users/me", headers=_auth(_token_for(None)))

    assert response.status_code == 401


def test_me_with_token_without_subject_returns_401(client: TestClient) -> None:
    """Токен без обязательного claim sub отклоняется."""
    now = datetime.now(timezone.utc)
    token = _encode({"iat": now, "exp": now + timedelta(minutes=30)})

    response = client.get("/users/me", headers=_auth(token))

    assert response.status_code == 401
