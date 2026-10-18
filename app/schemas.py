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
            "examples": [{"email": "ivan.petrov@example.com", "full_name": "Иван Петров"}]
        },
    )

    email: EmailStr = Field(description="Уникальный email", examples=["ivan.petrov@example.com"])
    full_name: str = Field(
        min_length=1, max_length=200, description="Полное имя", examples=["Иван Петров"]
    )


class UserRead(BaseModel):
    """Пользователь, возвращаемый API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    created_at: datetime
