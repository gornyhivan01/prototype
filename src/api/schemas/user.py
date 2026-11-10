"""Схемы пользователя."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRole(str, Enum):
    """Роль пользователя."""

    USER = "USER"
    ADMIN = "ADMIN"


class UserRead(BaseModel):
    """Пользователь, возвращаемый API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    role: UserRole
    created_at: datetime


class UserPage(BaseModel):
    """Страница списка пользователей."""

    total: int
    limit: int
    offset: int
    items: list[UserRead]


class RoleUpdate(BaseModel):
    """Новая роль пользователя."""

    role: UserRole = Field(description="Роль: USER или ADMIN")


class UserCreate(BaseModel):
    """Данные для создания пользователя администратором."""

    email: EmailStr = Field(description="Email", examples=["user@example.com"])
    password: str = Field(
        min_length=8,
        max_length=72,
        description="Пароль (8–72 символа; ограничение bcrypt)",
        examples=["secure123"],
    )
    name: str = Field(min_length=1, max_length=200, description="Имя", examples=["Иван Иванов"])
    role: UserRole = Field(default=UserRole.USER, description="Роль нового пользователя")
