"""Юнит-тесты безопасности: Argon2id, bcrypt-совместимость и JWT (без БД)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest

from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_hash_password_uses_argon2id() -> None:
    """Новые пароли хешируются Argon2id."""
    hashed = hash_password("secret123")

    assert hashed.startswith("$argon2id$")
    assert verify_password("secret123", hashed) is True
    assert needs_rehash(hashed) is False


def test_hash_password_is_salted() -> None:
    """Один и тот же пароль даёт разные хеши благодаря соли."""
    first = hash_password("secret123")
    second = hash_password("secret123")

    assert first != second
    assert verify_password("secret123", first)
    assert verify_password("secret123", second)


def test_legacy_bcrypt_hash_is_accepted() -> None:
    """Хеши прежних версий (bcrypt) продолжают приниматься."""
    legacy = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode("utf-8")

    assert verify_password("secret123", legacy) is True
    assert needs_rehash(legacy) is True


def test_verify_password_rejects_wrong_password() -> None:
    """Неверный пароль не проходит проверку."""
    hashed = hash_password("secret123")

    assert verify_password("secret124", hashed) is False


def test_verify_password_survives_broken_hash() -> None:
    """Битый хеш не роняет приложение, а просто не подтверждает пароль."""
    assert verify_password("secret123", "not-a-known-hash") is False


def test_access_token_roundtrip() -> None:
    """Токен кодируется и декодируется, ``sub`` сохраняется."""
    token = create_access_token("42")

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert "exp" in payload


def test_decode_rejects_expired_token() -> None:
    """Просроченный токен считается невалидным."""
    settings = get_settings()
    token = jwt.encode(
        {"sub": "42", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_decode_rejects_foreign_signature() -> None:
    """Токен с чужой подписью отклоняется."""
    settings = get_settings()
    token = jwt.encode({"sub": "42"}, "another-secret", algorithm=settings.jwt_algorithm)

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
