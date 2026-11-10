"""Сервис пользователей: регистрация, вход, профиль, управление доступом."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AuditAction, add_entry, log_entry, log_rejection
from src.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from src.core.security import hash_password, needs_rehash, verify_password
from src.models.user import User, UserRole
from src.repositories.task_repo import TaskRepository
from src.repositories.user_repo import UserRepository
from src.utils.unit_of_work import UnitOfWork


class UserService:
    """Бизнес-логика пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)
        self._tasks = TaskRepository(session)
        self._uow = UnitOfWork(session)

    async def register(
        self, *, email: str, password: str, name: str, ip_address: str | None = None
    ) -> User:
        """Регистрирует пользователя с ролью USER."""
        return await self._create(
            email=email,
            password=password,
            name=name,
            role=UserRole.USER,
            actor_id=None,
            ip_address=ip_address,
        )

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        name: str,
        role: UserRole,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        """Создаёт пользователя с заданной ролью (только администратор)."""
        return await self._create(
            email=email,
            password=password,
            name=name,
            role=role,
            actor_id=actor.id,
            ip_address=ip_address,
        )

    async def _create(
        self,
        *,
        email: str,
        password: str,
        name: str,
        role: UserRole,
        actor_id: int | None,
        ip_address: str | None,
    ) -> User:
        normalized = email.strip().lower()
        if await self._repo.get_by_email(normalized) is not None:
            log_rejection(
                action=AuditAction.USER_CREATED.value,
                email=normalized,
                ip_address=ip_address,
                reason="duplicate_email",
            )
            raise ConflictError("Пользователь с таким email уже существует")

        user = await self._repo.create(
            email=normalized,
            hashed_password=hash_password(password),
            name=name.strip(),
            role=role.value,
        )
        entry = add_entry(
            self._session,
            action=AuditAction.USER_CREATED,
            actor_id=actor_id,
            target_user_id=user.id,
            email=user.email,
            ip_address=ip_address,
        )
        await self._uow.commit()
        await self._session.refresh(user)
        log_entry(entry)
        return user

    async def authenticate(
        self, *, email: str, password: str, ip_address: str | None = None
    ) -> User:
        """Проверяет email и пароль, фиксируя успех или неудачу в аудите."""
        normalized = email.strip().lower()
        user = await self._repo.get_by_email(normalized)

        reason: str | None = None
        if user is None:
            reason = "unknown_email"
        elif not verify_password(password, user.hashed_password):
            reason = "invalid_password"

        if reason is not None or user is None:
            entry = add_entry(
                self._session,
                action=AuditAction.LOGIN_FAILED,
                email=normalized,
                ip_address=ip_address,
                details={"reason": reason},
            )
            await self._uow.commit()
            log_entry(entry)
            raise UnauthorizedError("Неверный email или пароль")

        # Легаси-хеш (bcrypt) прозрачно пересчитывается в Argon2id.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        entry = add_entry(
            self._session,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id=user.id,
            email=user.email,
            ip_address=ip_address,
        )
        await self._uow.commit()
        log_entry(entry)
        return user

    async def get_profile(self, user_id: int) -> User:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден")
        return user

    async def list_users(self, *, limit: int, offset: int) -> tuple[list[User], int]:
        users = await self._repo.list_all(limit=limit, offset=offset)
        total = await self._repo.count()
        return users, total

    async def change_role(
        self,
        *,
        user_id: int,
        role: UserRole,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден")
        previous = user.role
        await self._repo.set_role(user, role)
        entry = add_entry(
            self._session,
            action=AuditAction.USER_ROLE_CHANGED,
            actor_id=actor.id,
            target_user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            details={"from": previous, "to": role.value},
        )
        await self._uow.commit()
        await self._session.refresh(user)
        log_entry(entry)
        return user

    async def delete_user(self, *, admin: User, user_id: int, ip_address: str | None = None) -> int:
        """Удаляет пользователя, отправляя его задачи в архив.

        Возвращает число заархивированных задач.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден")
        if user.id == admin.id:
            raise BadRequestError("Нельзя удалить собственную учётную запись")
        if user.role == UserRole.ADMIN.value and await self._repo.count_admins() <= 1:
            raise BadRequestError("Нельзя удалить последнего администратора")

        entry = add_entry(
            self._session,
            action=AuditAction.USER_DELETED,
            actor_id=admin.id,
            target_user_id=user.id,
            email=user.email,
            ip_address=ip_address,
        )
        # Событие вставляется до удаления пользователя: FK обнулит
        # target_user_id, но сама запись останется в журнале.
        await self._session.flush()

        archived = await self._tasks.archive_by_owner(
            owner_id=user.id, email=user.email, archived_at=datetime.now(UTC)
        )
        entry.details = {"archived_tasks": archived}
        await self._repo.delete(user)
        await self._uow.commit()
        log_entry(entry)
        return archived
