"""Пароли и JWT.

Пароли хешируются SHA-256 (``hashlib``), access-токены — подписанные JWT
(``PyJWT``, алгоритм HS256).

.. warning::
   SHA-256 — быстрый криптографический хеш, он **не предназначен для паролей**:
   одинаковые пароли дают одинаковый хеш (соли нет), а высокая скорость
   облегчает перебор и атаки по радужным таблицам. В продакшене используйте
   Argon2id, bcrypt или PBKDF2 с большим числом итераций. Хеширование вынесено
   в две функции, поэтому смена алгоритма не затрагивает остальной код.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    """Возвращает SHA-256-хеш пароля в hex-виде (64 символа)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """Сравнивает пароль с сохранённым хешем за постоянное время.

    ``hmac.compare_digest`` не зависит от того, на каком символе хеши
    разошлись, поэтому не утекает информация о правильном префиксе.
    """
    return hmac.compare_digest(hash_password(password), stored_hash)


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
