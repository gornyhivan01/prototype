"""Модель пользователя."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.task import Task


class UserRole(str, enum.Enum):
    """Роль пользователя (RBAC)."""

    USER = "USER"
    ADMIN = "ADMIN"


class User(Base):
    """Пользователь сервиса."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('USER', 'ADMIN')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserRole.USER.value, server_default=UserRole.USER.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Задачи не удаляются вместе с пользователем: их архивирует сервис,
    # а FK с ON DELETE SET NULL обнуляет владельца.
    tasks: Mapped[list[Task]] = relationship(back_populates="owner", passive_deletes=True)
