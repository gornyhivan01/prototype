"""Репозиторий задач."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.task import Task


class TaskRepository:
    """Операции с таблицей tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _filtered(
        *,
        owner_id: int | None,
        status: str | None,
        priority: str | None,
        deadline_from: datetime | None,
        deadline_to: datetime | None,
        archived: bool,
    ) -> Select[tuple[Task]]:
        query = select(Task)
        # Активные и архивные задачи никогда не смешиваются в одном списке.
        query = query.where(
            Task.archived_at.is_not(None) if archived else Task.archived_at.is_(None)
        )
        if owner_id is not None:
            query = query.where(Task.user_id == owner_id)
        if status is not None:
            query = query.where(Task.status == status)
        if priority is not None:
            query = query.where(Task.priority == priority)
        if deadline_from is not None:
            query = query.where(Task.deadline >= deadline_from)
        if deadline_to is not None:
            query = query.where(Task.deadline <= deadline_to)
        return query

    async def list(
        self,
        *,
        owner_id: int | None,
        status: str | None,
        priority: str | None,
        deadline_from: datetime | None,
        deadline_to: datetime | None,
        archived: bool,
        limit: int,
        offset: int,
    ) -> list[Task]:
        query = self._filtered(
            owner_id=owner_id,
            status=status,
            priority=priority,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            archived=archived,
        ).order_by(Task.created_at.desc(), Task.id.desc())
        result = await self._session.scalars(query.limit(limit).offset(offset))
        return list(result)

    async def count(
        self,
        *,
        owner_id: int | None,
        status: str | None,
        priority: str | None,
        deadline_from: datetime | None,
        deadline_to: datetime | None,
        archived: bool,
    ) -> int:
        query = self._filtered(
            owner_id=owner_id,
            status=status,
            priority=priority,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            archived=archived,
        )
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        return total or 0

    async def get_by_id(self, task_id: int) -> Task | None:
        return await self._session.get(Task, task_id)

    async def create(self, *, owner_id: int, **fields: object) -> Task:
        task = Task(user_id=owner_id, **fields)
        self._session.add(task)
        await self._session.flush()
        return task

    async def archive_by_owner(self, *, owner_id: int, email: str, archived_at: datetime) -> int:
        """Переносит все задачи владельца в архив, сохраняя его email.

        Владелец обнуляется: пользователь удаляется, но история задач остаётся.
        """
        result = await self._session.execute(
            update(Task)
            .where(Task.user_id == owner_id)
            .values(archived_at=archived_at, archived_owner_email=email, user_id=None)
        )
        await self._session.flush()
        return result.rowcount or 0

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)
        await self._session.flush()
