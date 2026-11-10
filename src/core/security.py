"""Хеширование паролей (Argon2id), JWT-токены (PyJWT) и токены сессии."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from src.core.config import get_settings

# Новые пароли считаются Argon2id. Bcrypt оставлен вторым хешером, чтобы
# учётные записи прежних версий продолжали входить: после успешного входа
# хеш прозрачно пересчитывается в Argon2id (см. ``needs_rehash``).
_password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))

# Refresh-токен — случайная строка, в БД хранится только её SHA-256.
REFRESH_TOKEN_BYTES = 48
# CSRF-токен читается фронтендом из cookie и повторяется в заголовке.
CSRF_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Возвращает Argon2id-хеш пароля (у каждого пароля своя соль)."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Проверяет пароль против Argon2id- или легаси-bcrypt-хеша."""
    try:
        return _password_hash.verify(password, hashed_password)
    except UnknownHashError:
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Возвращает ``True``, если хеш посчитан не Argon2id и его пора обновить."""
    return not stored_hash.startswith("$argon2id$")


def create_access_token(subject: str) -> str:
    """Выпускает access-токен (JWT) для пользователя ``subject``."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Проверяет подпись и срок токена и возвращает payload."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def new_refresh_token() -> str:
    """Генерирует новый refresh-токен (случайная строка, не JWT)."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Возвращает SHA-256 refresh-токена: в БД хранится только он."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    """Генерирует CSRF-токен для схемы double-submit cookie."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)
