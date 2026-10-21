"""Пароли и JWT.

Пароли хешируются Argon2id через ``pwdlib``: у каждого пароля своя соль,
а параметры (память, число итераций) подобраны так, чтобы перебор был дорогим.
Хеширование вынесено в две функции, поэтому смена алгоритма не затрагивает
остальной код.
"""

from __future__ import annotations

import hashlib
import hmac
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


def _looks_like_sha256(value: str) -> bool:
    """Отличает хеш прежней версии (64 hex-символа) от Argon2id."""
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def verify_password(password: str, stored_hash: str) -> bool:
    """Проверяет пароль по сохранённому хешу.

    Пустой или повреждённый хеш считается несовпадением, а не ошибкой сервера.
    Хеши прежней версии (SHA-256) ещё принимаются — чтобы пользователи могли
    войти и обновить хеш (см. :func:`needs_rehash`).
    """
    try:
        return _password_hash.verify(password, stored_hash)
    except UnknownHashError:
        if _looks_like_sha256(stored_hash):
            legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(legacy_hash, stored_hash)
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Возвращает ``True``, если хеш создан не Argon2id и его пора обновить."""
    return not stored_hash.startswith("$argon2id$")


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
