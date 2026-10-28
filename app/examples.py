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
    "role": "user",
    "created_at": "2026-10-19T12:00:00Z",
}

# --- Именованные примеры тела запроса (POST /users, роль задаёт админ) ---
CREATE_USER_EXAMPLES: dict[str, Any] = {
    "russian": {
        "summary": "Пользователь с именем на русском",
        "value": {
            "email": "ivan.petrov@example.com",
            "full_name": "Иван Петров",
            "password": "secret123",
            "role": "user",
        },
    },
    "admin": {
        "summary": "Пользователь с ролью администратора",
        "value": {
            "email": "chief@example.com",
            "full_name": "Главный",
            "password": "secret123",
            "role": "admin",
        },
    },
}

# --- JWT (POST /auth/login) ---
TOKEN_EXAMPLE: dict[str, Any] = {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.example-signature",
    "token_type": "bearer",
    "expires_in": 1800,
}

# --- Примеры параметра пути (GET /users/{user_id}) ---
USER_ID_EXAMPLES: dict[str, Any] = {
    "existing": {"summary": "Существующий пользователь", "value": 1},
}

# --- Журнал аудита (GET /audit, GET /audit/me) ---
AUDIT_PAGE_EXAMPLE: dict[str, Any] = {
    "total": 2,
    "limit": 50,
    "offset": 0,
    "items": [
        {
            "id": 12,
            "action": "auth.login.success",
            "actor_id": 3,
            "target_user_id": 3,
            "email": "admin@example.com",
            "ip_address": "127.0.0.1",
            "details": {"via": "sso", "role": "admin"},
            "created_at": "2026-10-28T19:30:27Z",
        },
        {
            "id": 11,
            "action": "user.created",
            "actor_id": 3,
            "target_user_id": 7,
            "email": "ivan.petrov@example.com",
            "ip_address": "127.0.0.1",
            "details": None,
            "created_at": "2026-10-28T19:29:10Z",
        },
    ],
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
