"""CRUD задач с фильтрацией, пагинацией и проверкой прав."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status

from src.api.dependencies import CurrentUser, DbSession
from src.api.schemas.task import (
    TaskCreate,
    TaskPage,
    TaskPriority,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)
from src.core.audit import client_ip
from src.core.exceptions import ForbiddenError
from src.models.user import UserRole
from src.services.notification import send_task_created_email
from src.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])

Limit = Annotated[int, Query(ge=1, le=100, description="Размер страницы")]
Offset = Annotated[int, Query(ge=0, description="Сколько записей пропустить")]


@router.get("", response_model=TaskPage, summary="Список задач")
async def list_tasks(
    current_user: CurrentUser,
    session: DbSession,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: Annotated[TaskPriority | None, Query()] = None,
    deadline_from: Annotated[datetime | None, Query()] = None,
    deadline_to: Annotated[datetime | None, Query()] = None,
    archived: Annotated[
        bool, Query(description="Показать архив задач удалённых пользователей")
    ] = False,
    limit: Limit = 20,
    offset: Offset = 0,
) -> TaskPage:
    """Пользователь видит свои задачи, ADMIN — все; архив доступен только ADMIN."""
    if archived and current_user.role != UserRole.ADMIN.value:
        raise ForbiddenError("Недостаточно прав")

    items, total = await TaskService(session).list(
        user=current_user,
        status=status_filter.value if status_filter else None,
        priority=priority.value if priority else None,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        archived=archived,
        limit=limit,
        offset=offset,
    )
    return TaskPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[TaskRead.model_validate(task) for task in items],
    )


@router.post(
    "", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="Создать задачу"
)
async def create_task(
    payload: TaskCreate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TaskRead:
    """Создаёт задачу и ставит в фон «письмо» об email-уведомлении."""
    task = await TaskService(session).create(
        user=current_user,
        ip_address=client_ip(request),
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        priority=payload.priority.value,
        deadline=payload.deadline,
    )
    background_tasks.add_task(send_task_created_email, current_user.email, task.title)
    return TaskRead.model_validate(task)


@router.get("/{task_id}", response_model=TaskRead, summary="Задача по id")
async def get_task(task_id: int, current_user: CurrentUser, session: DbSession) -> TaskRead:
    """Возвращает задачу, если она доступна пользователю."""
    task = await TaskService(session).get(user=current_user, task_id=task_id)
    return TaskRead.model_validate(task)


@router.patch("/{task_id}", response_model=TaskRead, summary="Обновить задачу")
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> TaskRead:
    """Обновляет переданные поля задачи."""
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "status" in changes:
        changes["status"] = payload.status.value if payload.status else None
    if "priority" in changes:
        changes["priority"] = payload.priority.value if payload.priority else None
    task = await TaskService(session).update(
        user=current_user,
        task_id=task_id,
        changes=changes,
        ip_address=client_ip(request),
    )
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Удалить задачу",
)
async def delete_task(
    task_id: int, current_user: CurrentUser, session: DbSession, request: Request
) -> Response:
    """Удаляет задачу, если она доступна пользователю."""
    await TaskService(session).delete(
        user=current_user, task_id=task_id, ip_address=client_ip(request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
