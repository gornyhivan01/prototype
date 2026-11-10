"""Юнит-тесты валидации Pydantic-схем (без базы данных)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.schemas.auth import RegisterRequest
from src.api.schemas.task import TaskCreate, TaskPriority, TaskStatus, TaskUpdate


def test_task_create_uses_defaults() -> None:
    """Обязателен только заголовок, остальные поля имеют значения по умолчанию."""
    task = TaskCreate(title="Задача")

    assert task.status is TaskStatus.PENDING
    assert task.priority is TaskPriority.MEDIUM
    assert task.description is None
    assert task.deadline is None


def test_task_create_rejects_empty_title() -> None:
    """Пустой заголовок недопустим."""
    with pytest.raises(ValidationError):
        TaskCreate(title="")


def test_task_create_rejects_unknown_status() -> None:
    """Неизвестный статус не превращается в enum."""
    with pytest.raises(ValidationError):
        TaskCreate(title="Задача", status="archived")  # type: ignore[arg-type]


def test_task_update_allows_empty_payload() -> None:
    """PUT без изменений допустим: все поля опциональны."""
    update = TaskUpdate()

    assert update.model_dump(exclude_unset=True) == {}


def test_register_request_rejects_short_password() -> None:
    """Пароль короче 8 символов отклоняется."""
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="short", name="Имя")


def test_register_request_rejects_invalid_email() -> None:
    """Строка, не похожая на email, отклоняется."""
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="secret123", name="Имя")
