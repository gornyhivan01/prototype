"""Синхронизация пользователей сервиса с Keycloak (Admin REST API).

Вызывается из users-роутера: когда администратор создаёт или удаляет
пользователя через дашборд, учётка **также заводится/удаляется в реалме
Keycloak**. Иначе созданный пользователь не сможет войти через SSO — это два
независимых каталога (БД сервиса и реалм IdP).

Используется только стандартная библиотека (urllib). Пароль пользователя в
Keycloak задаётся тем же, что в сервисе, а роль `admin` выдаётся через
realm-роль `admin`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.config import get_settings
from app.models import ROLE_ADMIN

# Токен админа Keycloak кэшируется на это время.
_TOKEN_TTL_SECONDS = 55


class KeycloakAdminError(Exception):
    """Ошибка Admin REST Keycloak. Сообщение безопасно для клиента."""


_token_cache: dict[str, tuple[str, float]] = {}


def _http(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | list[Any] | None = None,
    token: str | None = None,
    as_json: bool = False,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body: bytes | None = None
    if data is not None:
        if as_json:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        else:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(  # noqa: S310 — URL строится только из локального dev-конфига
        url, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            payload = response.read()
            return json.loads(payload.decode()) if payload else {}
    except urllib.error.HTTPError as exc:
        raise KeycloakAdminError(f"Keycloak вернул HTTP {exc.code}") from exc
    except OSError as exc:
        raise KeycloakAdminError(f"Keycloak недоступен: {exc}") from exc


def _realm_url(settings: Any) -> str:
    base = settings.keycloak_url.rstrip("/")
    return f"{base}/admin/realms/{settings.keycloak_realm}"


def _admin_token(settings: Any) -> str:
    cached, cached_at = _token_cache.get(settings.keycloak_url, ("", 0.0))
    if cached and time.time() - cached_at < _TOKEN_TTL_SECONDS:
        return cached
    endpoint = f"{settings.keycloak_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "grant_type": "password",
        "username": settings.keycloak_admin_user,
        "password": settings.keycloak_admin_password,
    }
    try:
        response = _http("POST", endpoint, data=data)
    except KeycloakAdminError as exc:
        raise KeycloakAdminError("Не удалось получить токен админа Keycloak") from exc
    token = response.get("access_token", "")
    if not token:
        raise KeycloakAdminError("Keycloak не вернул токен админа")
    _token_cache[settings.keycloak_url] = (token, time.time())
    return token


def _find_user_id(settings: Any, token: str, email: str) -> str | None:
    query = urllib.parse.urlencode({"email": email, "exact": "true"})
    users = _http("GET", f"{_realm_url(settings)}/users?{query}", token=token)
    if not users:
        return None
    return users[0]["id"]


def _ensure_realm_role(settings: Any, token: str, name: str) -> dict[str, Any]:
    url = f"{_realm_url(settings)}/roles/{name}"
    try:
        return _http("GET", url, token=token)
    except KeycloakAdminError:
        _http(
            "POST",
            f"{_realm_url(settings)}/roles",
            data={"name": name, "description": "Администратор сервиса"},
            token=token,
            as_json=True,
        )
        return _http("GET", url, token=token)


def create_keycloak_user(email: str, password: str, full_name: str, role: str) -> None:
    """Заводит (или приводит к нужному состоянию) учётку в Keycloak."""
    settings = get_settings()
    token = _admin_token(settings)

    first, _, last = full_name.partition(" ")
    payload = {
        "username": email,
        "email": email,
        "enabled": True,
        "emailVerified": True,
        "firstName": first or email.split("@")[0],
        "lastName": last or "SSO",
        "requiredActions": [],
    }
    user_id = _find_user_id(settings, token, email)
    if user_id is None:
        _http("POST", f"{_realm_url(settings)}/users", data=payload, token=token, as_json=True)
        user_id = _find_user_id(settings, token, email)
    if user_id is None:
        raise KeycloakAdminError("Не удалось создать пользователя в Keycloak")

    _http(
        "PUT",
        f"{_realm_url(settings)}/users/{user_id}/reset-password",
        data={"type": "password", "value": password, "temporary": False},
        token=token,
        as_json=True,
    )

    if role == ROLE_ADMIN:
        admin_role = _ensure_realm_role(settings, token, ROLE_ADMIN)
        _http(
            "POST",
            f"{_realm_url(settings)}/users/{user_id}/role-mappings/realm",
            data=[{"id": admin_role["id"], "name": admin_role["name"]}],
            token=token,
            as_json=True,
        )


def delete_keycloak_user(email: str) -> None:
    """Удаляет учётку из Keycloak (если она там есть)."""
    settings = get_settings()
    token = _admin_token(settings)
    user_id = _find_user_id(settings, token, email)
    if user_id is None:
        return
    _http("DELETE", f"{_realm_url(settings)}/users/{user_id}", token=token)
