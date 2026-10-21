"""Pydantic-схемы запросов и ответов.

Примеры (``examples``) отображаются в Swagger UI на ``/docs``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Данные для создания пользователя."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "email": "ivan.petrov@example.com",
                    "full_name": "Иван Петров",
                    "password": "secret123",
                }
            ]
        },
    )

    email: EmailStr = Field(description="Уникальный email", examples=["ivan.petrov@example.com"])
    full_name: str = Field(
        min_length=1, max_length=200, description="Полное имя", examples=["Иван Петров"]
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Пароль (8–128 символов); хранится только как SHA-256-хеш",
        examples=["secret123"],
    )


class UserRead(BaseModel):
    """Пользователь, возвращаемый API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    created_at: datetime


class Token(BaseModel):
    """Ответ с access-токеном (OAuth2 Bearer)."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 — имя поля по стандарту OAuth2
    expires_in: int = Field(description="Срок жизни токена в секундах", examples=[1800])
