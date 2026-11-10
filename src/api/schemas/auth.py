"""Схемы аутентификации."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Данные для регистрации."""

    email: EmailStr = Field(description="Email", examples=["user@example.com"])
    password: str = Field(
        min_length=8,
        max_length=72,
        description="Пароль (8–72 символа; ограничение bcrypt)",
        examples=["secure123"],
    )
    name: str = Field(min_length=1, max_length=200, description="Имя", examples=["Иван Иванов"])


class LoginRequest(BaseModel):
    """Данные для входа."""

    email: EmailStr = Field(examples=["user@example.com"])
    password: str = Field(min_length=1, max_length=72, examples=["secure123"])


class TokenResponse(BaseModel):
    """Ответ с access-токеном."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 — имя поля по стандарту OAuth2
    expires_in: int = Field(description="Срок жизни токена в секундах", examples=[1800])
