"""Схемы задач."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Статус задачи."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, Enum):
    """Приоритет задачи."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskCreate(BaseModel):
    """Данные для создания задачи."""

    title: str = Field(min_length=1, max_length=200, description="Заголовок")
    description: str | None = Field(default=None, description="Описание")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Статус")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Приоритет")
    deadline: datetime | None = Field(default=None, description="Дедлайн")


class TaskUpdate(BaseModel):
    """Обновление задачи: все поля опциональны."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    deadline: datetime | None = None


class TaskRead(BaseModel):
    """Задача, возвращаемая API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    deadline: datetime | None
    user_id: int | None
    archived_at: datetime | None = Field(
        default=None, description="Когда задача попала в архив (None — активна)"
    )
    archived_owner_email: str | None = Field(
        default=None, description="Email владельца на момент архивации"
    )
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    """Страница списка задач."""

    total: int
    limit: int
    offset: int
    items: list[TaskRead]
