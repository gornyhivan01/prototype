"""Репозиторий пользователей."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User, UserRole


class UserRepository:
    """Операции с таблицей users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def create(self, *, email: str, hashed_password: str, name: str, role: str) -> User:
        user = User(email=email, hashed_password=hashed_password, name=name, role=role)
        self._session.add(user)
        await self._session.flush()
        return user

    async def list_all(self, *, limit: int, offset: int) -> list[User]:
        result = await self._session.scalars(
            select(User).order_by(User.id).limit(limit).offset(offset)
        )
        return list(result)

    async def count(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(User)) or 0

    async def count_admins(self) -> int:
        """Сколько администраторов осталось (нужно перед удалением)."""
        return (
            await self._session.scalar(
                select(func.count()).select_from(User).where(User.role == UserRole.ADMIN.value)
            )
            or 0
        )

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()

    async def set_role(self, user: User, role: UserRole) -> User:
        user.role = role.value
        await self._session.flush()
        return user
