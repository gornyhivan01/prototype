"""Тесты SSO: PKCE, проверка id_token и callback-эндпоинт.

id_token проверяется без сети: discovery и JWKS подменяются фейковыми,
подпись — реальным RSA-ключом, сгенерированным на месте.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import sso
from app.config import get_settings
from app.models import User

ISSUER = "http://localhost:8080/realms/prototype"
CLIENT_ID = "prototype-web"
KID = "test-key-1"


# ---------------------------------------------------------------------------
# Помощники: RSA-ключ и фейковый JWKS-клиент
# ---------------------------------------------------------------------------


def _b64url_int(value: int) -> str:
    length = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode().rstrip("=")


def _make_rsa():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    numbers = public.public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_int(numbers.n),
        "e": _b64url_int(numbers.e),
    }
    return private, public, jwk


class _FakeSigningKey:
    def __init__(self, public_key: Any) -> None:
        self.key = public_key


class _FakeJwksClient:
    """Имитирует jwt.PyJWKClient: возвращает заданный ключ без сети."""

    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        return _FakeSigningKey(self._public_key)


@pytest.fixture
def fake_idp(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, dict[str, Any]]:
    """Прописывает фейковый discovery и JWKS в модуль sso.

    Возвращает (private, public, claims_overrides_создателя).
    """
    private, public, jwk = _make_rsa()
    settings = get_settings()

    monkeypatch.setitem(
        sso._discovery_cache,
        settings.keycloak_url,
        {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
            "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
            "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
        },
    )
    monkeypatch.setitem(sso._jwks_clients, settings.keycloak_url, _FakeJwksClient(public))
    yield private, public, jwk


def _encode_id_token(private: Any, **overrides: Any) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "a0f7-9d1c",
        "exp": now + 300,
        "iat": now - 5,
        "nonce": "fixed-nonce",
        "email": "sso.user@example.com",
        "name": "SSO User",
    }
    payload.update(overrides)
    return jwt.encode(payload, private, algorithm="RS256", headers={"kid": KID})


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------


def test_code_verifier_has_expected_length() -> None:
    verifier = sso.create_code_verifier()
    assert len(verifier) == 43
    assert sso.create_s256_challenge(verifier)


def test_s256_challenge_is_deterministic() -> None:
    verifier = sso.create_code_verifier()
    assert sso.create_s256_challenge(verifier) == sso.create_s256_challenge(verifier)


def test_state_store_used_and_pruned(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setitem(
        sso._discovery_cache,
        settings.keycloak_url,
        {"authorization_endpoint": "http://idp/auth", "issuer": ISSUER},
    )
    sso._state_store.clear()
    url, state = sso.create_authorization_url()
    assert "code_challenge_method=S256" in url
    assert "state=" in url and "nonce=" in url
    assert state in sso._state_store
    sso._state_store.clear()


# ---------------------------------------------------------------------------
# Валидация id_token
# ---------------------------------------------------------------------------


def test_validate_accepts_valid_token(fake_idp: Any) -> None:
    private = fake_idp[0]
    claims = sso.validate_id_token(_encode_id_token(private), expected_nonce="fixed-nonce")
    assert claims["email"] == "sso.user@example.com"


def test_validate_rejects_wrong_audience(fake_idp: Any) -> None:
    private = fake_idp[0]
    token = _encode_id_token(private, aud="other-client")
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(token, expected_nonce="fixed-nonce")


def test_validate_rejects_expired(fake_idp: Any) -> None:
    private = fake_idp[0]
    token = _encode_id_token(private, exp=int(time.time()) - 60)
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(token, expected_nonce="fixed-nonce")


def test_validate_rejects_wrong_nonce(fake_idp: Any) -> None:
    private = fake_idp[0]
    token = _encode_id_token(private)
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(token, expected_nonce="another-nonce")


def test_validate_rejects_tampered_signature(fake_idp: Any) -> None:
    private = fake_idp[0]
    token = _encode_id_token(private)
    tampered = token[:-6] + "ABCDEF"
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(tampered, expected_nonce="fixed-nonce")


# ---------------------------------------------------------------------------
# Callback-эндпоинт
# ---------------------------------------------------------------------------


def test_sso_start_redirects(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(sso, "create_authorization_url", lambda: ("http://idp/auth?x=1", "state-1"))
    response = client.get("/auth/sso/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "http://idp/auth?x=1"


def test_callback_creates_user_and_issues_token(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db_session: Session,
) -> None:
    claims = {
        "sub": "a0f7-9d1c",
        "email": "sso.user@example.com",
        "name": "SSO User",
    }
    monkeypatch.setattr(sso, "exchange_id_token_claims", lambda **_: claims)

    response = client.get("/auth/sso/callback?code=abc&state=xyz")
    assert response.status_code == 200
    assert "Вход выполнен" in response.text

    user = db_session.scalar(select(User).where(User.email == "sso.user@example.com"))
    assert user is not None
    assert user.full_name == "SSO User"
    # Пароль SSO-пользователя не может быть проверен по подсказке формата Argon2.
    assert user.hashed_password.startswith("$argon2id$")


def test_callback_uses_existing_user_without_double_registration(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db_session: Session,
) -> None:
    from app.security import hash_password

    existing = User(
        email="sso.user@example.com",
        full_name="Уже есть",
        hashed_password=hash_password("password123"),
    )
    db_session.add(existing)
    db_session.commit()

    claims = {"sub": "a0f7-9d1c", "email": "sso.user@example.com", "name": "SSO User"}
    monkeypatch.setattr(sso, "exchange_id_token_claims", lambda **_: claims)
    client.get("/auth/sso/callback?code=abc&state=xyz")

    users = db_session.scalars(select(User).where(User.email == "sso.user@example.com")).all()
    assert len(users) == 1
    assert users[0].full_name == "Уже есть"


def test_callback_rejects_invalid_state(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    def fail(**_: Any) -> dict[str, Any]:
        raise sso.SsoError("Сессия SSO не найдена или истекла")

    monkeypatch.setattr(sso, "exchange_id_token_claims", fail)
    response = client.get("/auth/sso/callback?code=abc&state=broken")
    assert response.status_code == 400
    assert "Не удалось войти" in response.text
