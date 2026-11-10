"""Жизненный цикл cookie-сессии: выдача, ротация и отзыв токенов.

Access-токен — короткоживущий JWT (отозвать его нельзя, поэтому срок мал).
Refresh-токен хранится в БД в виде SHA-256 и при каждом обновлении меняется:
старый отзывается, выдаётся новый. Повторное предъявление отозванного токена
трактуется как кража — тогда отзываются все сессии пользователя.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AuditAction, add_entry, log_entry
from src.core.config import Settings, get_settings
from src.core.security import (
    create_access_token,
    hash_refresh_token,
    new_csrf_token,
    new_refresh_token,
)
from src.models.refresh_token import RefreshToken
from src.models.user import User
from src.repositories.token_repo import RefreshTokenRepository
from src.utils.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class SessionTokens:
    """Токены, которые кладутся в cookie после входа или обновления."""

    access_token: str
    refresh_token: str
    csrf_token: str
    expires_in: int


class SessionService:
    """Выдаёт, ротирует и отзывает сессии входа."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._repo = RefreshTokenRepository(session)
        self._uow = UnitOfWork(session)
        self._settings = settings or get_settings()

    async def start(self, *, user: User) -> SessionTokens:
        """Создаёт новую сессию и возвращает токены для cookie."""
        tokens = await self._issue(user)
        await self._uow.commit()
        return tokens

    async def rotate(
        self, *, refresh_token: str, ip_address: str | None = None
    ) -> tuple[User, SessionTokens] | None:
        """Меняет refresh-токен на новый; при повторном использовании — отзывает всё."""
        stored = await self._repo.get_by_hash(hash_refresh_token(refresh_token))
        if stored is None:
            return None

        now = datetime.now(UTC)

        if stored.revoked_at is not None:
            await self._handle_reuse(stored, ip_address=ip_address)
            return None

        if stored.expires_at <= now:
            await self._repo.revoke(stored, now)
            await self._uow.commit()
            return None

        user = await self._session.get(User, stored.user_id)
        if user is None:
            return None

        await self._repo.revoke(stored, now)
        tokens = await self._issue(user)
        await self._uow.commit()
        return user, tokens

    async def revoke(self, *, refresh_token: str, ip_address: str | None = None) -> bool:
        """Отзывает текущую сессию (выход). Возвращает ``False``, если токен неизвестен."""
        stored = await self._repo.get_by_hash(hash_refresh_token(refresh_token))
        if stored is None:
            return False
        if stored.revoked_at is None:
            await self._repo.revoke(stored, datetime.now(UTC))

        user = await self._session.get(User, stored.user_id)
        entry = add_entry(
            self._session,
            action=AuditAction.LOGOUT,
            actor_id=stored.user_id,
            email=user.email if user is not None else None,
            ip_address=ip_address,
        )
        await self._uow.commit()
        log_entry(entry)
        return True

    async def _issue(self, user: User) -> SessionTokens:
        """Создаёт refresh-запись и собирает пару токенов."""
        raw_refresh = new_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days)
        await self._repo.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=expires_at,
        )
        return SessionTokens(
            access_token=create_access_token(str(user.id)),
            refresh_token=raw_refresh,
            csrf_token=new_csrf_token(),
            expires_in=self._settings.access_token_expire_minutes * 60,
        )

    async def _handle_reuse(self, stored: RefreshToken, *, ip_address: str | None) -> None:
        """Реагирует на повторное предъявление отозванного токена."""
        revoked = await self._repo.revoke_all_for_user(stored.user_id, datetime.now(UTC))
        entry = add_entry(
            self._session,
            action=AuditAction.TOKEN_REUSED,
            target_user_id=stored.user_id,
            ip_address=ip_address,
            details={"revoked_sessions": revoked},
        )
        await self._uow.commit()
        log_entry(entry)
