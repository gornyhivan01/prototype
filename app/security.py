"""Пароли и JWT.

Пароли хранятся только в виде Argon2id-хеша (``pwdlib``), access-токены —
подписанные JWT (``PyJWT``, алгоритм HS256).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.config import get_settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Возвращает Argon2id-хеш пароля (соль генерируется автоматически)."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль по сохранённому хешу.

    Пустой или повреждённый хеш считается несовпадением, а не ошибкой сервера.
    """
    try:
        return _password_hash.verify(password, password_hash)
    except UnknownHashError:
        return False


def create_access_token(subject: str) -> str:
    """Выпускает access-токен (JWT) для пользователя ``subject``."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Проверяет подпись и срок действия токена и возвращает payload."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
