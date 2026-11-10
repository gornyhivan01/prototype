"""Сервис задач: CRUD и проверка прав."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AuditAction, add_entry, log_entry
from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.task import Task
from src.models.user import User, UserRole
from src.repositories.task_repo import TaskRepository
from src.utils.unit_of_work import UnitOfWork


class TaskService:
    """Бизнес-логика задач: пользователь работает со своими, ADMIN — со всеми."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TaskRepository(session)
        self._uow = UnitOfWork(session)

    def _visible_owner_id(self, user: User) -> int | None:
        """ADMIN видит все задачи, остальные — только свои."""
        return None if user.role == UserRole.ADMIN.value else user.id

    async def _get_accessible(self, *, user: User, task_id: int) -> Task:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError("Задача не найдена")
        if user.role != UserRole.ADMIN.value and task.user_id != user.id:
            raise ForbiddenError("Недостаточно прав")
        return task

    async def list(
        self,
        *,
        user: User,
        status: str | None = None,
        priority: str | None = None,
        deadline_from: datetime | None = None,
        deadline_to: datetime | None = None,
        archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        owner_id = self._visible_owner_id(user)
        items = await self._repo.list(
            owner_id=owner_id,
            status=status,
            priority=priority,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            archived=archived,
            limit=limit,
            offset=offset,
        )
        total = await self._repo.count(
            owner_id=owner_id,
            status=status,
            priority=priority,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            archived=archived,
        )
        return items, total

    async def create(self, *, user: User, ip_address: str | None = None, **fields: object) -> Task:
        task = await self._repo.create(owner_id=user.id, **fields)
        entry = add_entry(
            self._session,
            action=AuditAction.TASK_CREATED,
            actor_id=user.id,
            email=user.email,
            ip_address=ip_address,
            details={"task_id": task.id, "title": task.title},
        )
        await self._uow.commit()
        await self._session.refresh(task)
        log_entry(entry)
        return task

    async def get(self, *, user: User, task_id: int) -> Task:
        return await self._get_accessible(user=user, task_id=task_id)

    async def update(
        self,
        *,
        user: User,
        task_id: int,
        changes: dict[str, object],
        ip_address: str | None = None,
    ) -> Task:
        task = await self._get_accessible(user=user, task_id=task_id)
        for field, value in changes.items():
            setattr(task, field, value)
        entry = add_entry(
            self._session,
            action=AuditAction.TASK_UPDATED,
            actor_id=user.id,
            email=user.email,
            ip_address=ip_address,
            # Только имена полей: значения могут содержать datetime,
            # а колонка details — JSON.
            details={"task_id": task.id, "fields": sorted(changes)},
        )
        await self._uow.commit()
        await self._session.refresh(task)
        log_entry(entry)
        return task

    async def delete(self, *, user: User, task_id: int, ip_address: str | None = None) -> None:
        task = await self._get_accessible(user=user, task_id=task_id)
        entry = add_entry(
            self._session,
            action=AuditAction.TASK_DELETED,
            actor_id=user.id,
            email=user.email,
            ip_address=ip_address,
            details={"task_id": task.id, "title": task.title},
        )
        await self._repo.delete(task)
        await self._uow.commit()
        log_entry(entry)
