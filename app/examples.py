"""Примеры для OpenAPI — отображаются в Swagger UI на ``/docs``.

Вынесены в отдельный модуль, чтобы описания ручек в роутерах оставались
читаемыми.
"""

from __future__ import annotations

from typing import Any

# --- Успешные ответы ---
HEALTH_EXAMPLE: dict[str, Any] = {"status": "ok"}

USER_CREATED_EXAMPLE: dict[str, Any] = {
    "id": 1,
    "email": "ivan.petrov@example.com",
    "full_name": "Иван Петров",
    "created_at": "2026-10-19T12:00:00Z",
}

# --- Именованные примеры тела запроса (POST /users) ---
CREATE_USER_EXAMPLES: dict[str, Any] = {
    "russian": {
        "summary": "Пользователь с именем на русском",
        "value": {
            "email": "ivan.petrov@example.com",
            "full_name": "Иван Петров",
            "password": "secret123",
        },
    },
    "latin": {
        "summary": "Пользователь с латинским именем",
        "value": {
            "email": "john.doe@example.com",
            "full_name": "John Doe",
            "password": "secret123",
        },
    },
}

# --- JWT (POST /auth/login) ---
TOKEN_EXAMPLE: dict[str, Any] = {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.example-signature",
    "token_type": "bearer",
}

# --- Примеры параметра пути (GET /users/{user_id}) ---
USER_ID_EXAMPLES: dict[str, Any] = {
    "existing": {"summary": "Существующий пользователь", "value": 1},
}

# --- Переиспользуемые ответы с ошибками ---
NOT_FOUND_RESPONSE: dict[str, Any] = {
    "description": "Пользователь с указанным id не найден",
    "content": {"application/json": {"example": {"detail": "Пользователь не найден"}}},
}

CONFLICT_RESPONSE: dict[str, Any] = {
    "description": "Пользователь с таким email уже существует",
    "content": {
        "application/json": {"example": {"detail": "Пользователь с таким email уже существует"}}
    },
}

INVALID_CREDENTIALS_RESPONSE: dict[str, Any] = {
    "description": "Неверный email или пароль",
    "content": {"application/json": {"example": {"detail": "Неверный email или пароль"}}},
}

UNAUTHORIZED_RESPONSE: dict[str, Any] = {
    "description": "Токен отсутствует или недействителен",
    "content": {"application/json": {"example": {"detail": "Не удалось проверить токен"}}},
}

VALIDATION_RESPONSE: dict[str, Any] = {
    "description": "Ошибка валидации входных данных",
    "content": {
        "application/json": {
            "example": {
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body", "email"],
                        "msg": (
                            "value is not a valid email address: "
                            "An email address must have an @-sign."
                        ),
                        "input": "not-an-email",
                    }
                ]
            }
        }
    },
}
