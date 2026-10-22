"""OIDC-клиент для SSO через Keycloak (гибридная схема).

Вход выполняется в Keycloak, а сервис после успешной аутентификации выпускает
**свой** access-токен — ровно как `POST /auth/login`. Это позволяет оставить
неизменными остальные части приложения (`app.dependencies`, защиту ручек).

Поток:

1. `GET /auth/sso/start` — создаём `state`/`nonce`/PKCE-verifier и редиректим
   в Keycloak (authorization_code + PKCE S256).
2. Keycloak аутентифицирует пользователя и возвращает браузер на callback
   с кодом авторизации.
3. `GET /auth/sso/callback` — обмениваем код на токены, проверяем `id_token`
   (подпись RS256 по JWKS + `iss`/`aud`/`exp`/`nonce`), находим или создаём
   пользователя по email и выдаём свой JWT.

Сессии:`state`/`nonce`/verifier хранятся в памяти процесса (однопроцессный
dev-режим). Для мультипроцессной постановки нужен общий store (Redis и т.п.).

Преднамеренно не используем стороннюю библиотеку OIDC: обмен по RFC 6749 и
проверка JWT по RFC 7519/7517 — маленький и понятный код, удобный для учебного
проекта. Сетевые вызовы — через httpx, JWT — через pyjwt (уже в зависимостях).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import Settings, get_settings

# Сколько живёт сессия SSO (state/nonce/verifier) на нашем сервере.
AUTH_STATE_TTL_SECONDS = 600

# Время, на которое можно "уехать в прошлое" при проверке exp/iat (часовой сдвиг).
CLOCK_SKEW_SECONDS = 30


class SsoError(Exception):
    """Ошибка интеграции с IdP.

    Сообщение безопасно показать клиенту: в него не попадают внутренние детали
    (исключения httpx/pyjwt логируются отдельно).
    """


class PendingAuthorization:
    """Сохранённые между /sso/start и /sso/callback параметры защиты."""

    def __init__(
        self,
        *,
        nonce: str,
        code_verifier: str,
        redirect_uri: str,
        created_at: float,
    ) -> None:
        self.nonce = nonce
        self.code_verifier = code_verifier
        self.redirect_uri = redirect_uri
        self.created_at = created_at


# state -> PendingAuthorization. Хранилище в памяти: для учебного проекта и
# одного процесса uvicorn этого достаточно.
_state_store: dict[str, PendingAuthorization] = {}
_discovery_cache: dict[str, dict[str, Any]] = {}
_jwks_clients: dict[str, Any] = {}
_http: httpx.Client | None = None


def _get_http() -> httpx.Client:
    """Общий HTTP-клиент с таймаутами (медленный IdP не должен вешать запрос)."""
    global _http
    if _http is None:
        _http = httpx.Client(timeout=10.0, follow_redirects=False)
    return _http


def _prune_states() -> None:
    """Удаляет устаревшие SSO-сессии."""
    cutoff = time.time() - AUTH_STATE_TTL_SECONDS
    expired = [key for key, value in _state_store.items() if value.created_at < cutoff]
    for key in expired:
        _state_store.pop(key, None)


# ---------------------------------------------------------------------------
# PKCE (RFC 7636)
# ---------------------------------------------------------------------------


def _b64url(raw: bytes) -> str:
    """Base64url без символов '=' — требования PKCE."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def create_code_verifier() -> str:
    """Случайный verifier (43 символа из алфавита RFC 3986 unreserved)."""
    return _b64url(secrets.token_bytes(32))


def create_s256_challenge(verifier: str) -> str:
    """S256-челлендж для verifier."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


# ---------------------------------------------------------------------------
# Discovery IdP (OpenID Configuration, кэшируется)
# ---------------------------------------------------------------------------


def _issuer(settings: Settings) -> str:
    return f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"


def _discovery(settings: Settings) -> dict[str, Any]:
    """Читает и кэширует /.well-known/openid-configuration."""
    cached = _discovery_cache.get(settings.keycloak_url)
    if cached is not None:
        return cached
    issuer = _issuer(settings)
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        response = _get_http().get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SsoError("Не удалось получить конфигурацию провайдера") from exc
    metadata = response.json()
    if metadata.get("issuer") != issuer:
        raise SsoError("Провайдер вернул неожиданный issuer")
    _discovery_cache[settings.keycloak_url] = metadata
    return metadata


# ---------------------------------------------------------------------------
# state / start-поток
# ---------------------------------------------------------------------------


def create_authorization_url() -> tuple[str, str]:
    """Строит URL перенаправления в Keycloak. Возвращает (url, state)."""
    settings = get_settings()
    metadata = _discovery(settings)

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    code_verifier = create_code_verifier()
    auth_url = metadata["authorization_endpoint"]

    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.keycloak_client_id,
            "redirect_uri": settings.sso_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": create_s256_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )

    _prune_states()
    _state_store[state] = PendingAuthorization(
        nonce=nonce,
        code_verifier=code_verifier,
        redirect_uri=settings.sso_redirect_uri,
        created_at=time.time(),
    )
    return f"{auth_url}?{query}", state


# ---------------------------------------------------------------------------
# callback-поток
# ---------------------------------------------------------------------------


def _exchange_code(
    metadata: dict[str, Any],
    settings: Settings,
    *,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Обменивает авторизационный код на токены (RFC 6749) с PKCE."""
    try:
        response = _get_http().post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "code_verifier": verifier,
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SsoError("Провайдер отклонил обмен кода на токены") from exc
    return response.json()


def _signing_key_for(token: str, settings: Settings) -> str:
    """Возвращает публичный ключ (PEM) для проверки подписи id_token.

    Кэширует PyJWKClient (HTTP-запрос за JWKS выполняется только при смене
    ключа, PyJWT сам обращается к jwks_uri).
    """
    metadata = _discovery(settings)
    client = _jwks_clients.get(settings.keycloak_url)
    if client is None:
        client = jwt.PyJWKClient(metadata["jwks_uri"])
        _jwks_clients[settings.keycloak_url] = client
    signing_key = client.get_signing_key_from_jwt(token)
    return signing_key.key  # type: ignore[return-value]


def validate_id_token(id_token: str, expected_nonce: str) -> dict[str, Any]:
    """Проверяет id_token и возвращает его claims.

    Проверяется: подпись (RS256, ключ из JWKS IdP), `iss`, `aud`, `exp`,
    `iat`, срок действия и `nonce` (анти-replay). При малейшем отклонении —
    :class:`SsoError`.
    """
    settings = get_settings()
    try:
        public_key = _signing_key_for(id_token, settings)
    except SsoError:
        raise
    except Exception as exc:  # не найден ключ по kid, сеть и т.п.
        raise SsoError("Не удалось получить ключ подписи провайдера") from exc

    try:
        claims = jwt.decode(
            id_token,
            key=public_key,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
            issuer=_issuer(settings),
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
    except jwt.InvalidTokenError as exc:
        raise SsoError("ID-токен провайдера не прошёл проверку") from exc

    # nonce проверяется явно: PyJWT его не сравнивает, только требует наличие.
    if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise SsoError("Nonce токена не совпал с ожидаемым")
    return claims


def exchange_id_token_claims(*, code: str, state: str, request_url: str) -> dict[str, Any]:
    """Полный шаг callback: state -> код -> токены -> проверенные claims.

    Состояние из хранилища удаляется после использования (single-use), а
    параметр ``code`` можно использовать только один раз у самого IdP.
    """
    settings = get_settings()
    _prune_states()
    pending = _state_store.pop(state, None)
    if pending is None:
        raise SsoError("Сессия SSO не найдена или истекла")

    expected_redirect = pending.redirect_uri
    if not request_url.startswith(expected_redirect):
        raise SsoError("Callback пришёл с неожиданного адреса")

    metadata = _discovery(settings)
    tokens = _exchange_code(
        metadata,
        settings,
        code=code,
        verifier=pending.code_verifier,
        redirect_uri=pending.redirect_uri,
    )
    if "id_token" not in tokens:
        raise SsoError("Провайдер не вернул ID-токен")
    return validate_id_token(tokens["id_token"], pending.nonce)
