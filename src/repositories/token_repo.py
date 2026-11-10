"""Репозиторий refresh-токенов."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """Операции с таблицей refresh_tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: int, token_hash: str, expires_at: datetime) -> RefreshToken:
        """Сохраняет хеш нового refresh-токена."""
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Ищет сессию по хешу предъявленного токена."""
        return await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    async def revoke(self, token: RefreshToken, revoked_at: datetime) -> None:
        """Помечает конкретный токен отозванным."""
        token.revoked_at = revoked_at
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: int, revoked_at: datetime) -> int:
        """Отзывает все активные сессии пользователя; возвращает их число."""
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        return result.rowcount or 0

    async def count_active(self, user_id: int) -> int:
        """Сколько активных (не отозванных) сессий у пользователя."""
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            )
            or 0
        )
