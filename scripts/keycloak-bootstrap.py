#!/usr/bin/env python3
"""Создаёт роли и пользователей SSO в реалме ``prototype`` Keycloak.

Запуск (после ``docker compose up -d keycloak``):

    python scripts/keycloak-bootstrap.py

Скрипт идемпотентен: повторный запуск не создаёт дублей, а сбрасывает пароли.

Использует только стандартную библиотеку (urllib) — без внешних зависимостей.
После выполнения:

    Администратор: admin@example.com  / password123   (роль admin)
    Обычный        sso.user@example.com / password123  (роль user)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

KEYCLOAK_URL = "http://localhost:8080"
REALM = "prototype"

ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"  # noqa: S105 — dev-админ Keycloak (docker-compose)

ADMIN_ROLE = "admin"

ACCOUNTS = [
    {"email": "admin@example.com", "password": "password123", "role": ADMIN_ROLE},
    {"email": "sso.user@example.com", "password": "password123", "role": "user"},
]


class Unreachable(Exception):
    """Keycloak ещё не поднялся (или недоступен)."""


def _request(
    method: str,
    url: str,
    *,
    data: dict | list | None = None,
    token: str | None = None,
    as_json: bool = False,
) -> Any:
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
    request = urllib.request.Request(  # noqa: S310 — URL берётся только из локального dev-конфига
        url, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            payload = response.read()
            if not payload:
                return {}
            return json.loads(payload)
    except OSError as exc:
        if isinstance(exc, urllib.error.HTTPError):
            raise  # HTTP-ошибку обрабатывает вызывающий код
        raise Unreachable(f"Сеть не ответила ({url}): {exc}") from exc


def wait_for_ready(timeout_seconds: int = 120) -> None:
    """Ждёт, пока реалм начнёт отвечать на discovery-запрос."""
    url = f"{KEYCLOAK_URL}/realms/{REALM}/.well-known/openid-configuration"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            _request("GET", url)
            return
        except (Unreachable, urllib.error.URLError, urllib.error.HTTPError):
            time.sleep(3)
    raise Unreachable(f"Keycloak не ответил за {timeout_seconds}с: {url}")


def admin_token() -> str:
    """Токен админа из реалма master (клиент admin-cli)."""
    endpoint = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    payload = {
        "client_id": "admin-cli",
        "grant_type": "password",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
    }
    try:
        response = _request("POST", endpoint, data=payload)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Не удалось получить токен админа: HTTP {exc.code}")
    except Unreachable as exc:
        sys.exit(str(exc))
    return response["access_token"]


def ensure_realm_role(token: str, role_name: str) -> dict:
    """Создаёт realm-роль, если её нет, и возвращает её."""
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles/{role_name}"
    try:
        return _request("GET", url, token=token)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    _request(
        "POST",
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles",
        data={"name": role_name, "description": "Администратор сервиса"},
        token=token,
        as_json=True,
    )
    return _request("GET", url, token=token)


def find_user(token: str, email: str) -> dict | None:
    """Ищет пользователя по email в реалме ``prototype``."""
    query = urllib.parse.urlencode({"email": email, "exact": "true"})
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?{query}"
    users = _request("GET", url, token=token)
    return users[0] if users else None


def ensure_user(token: str, email: str) -> dict:
    """Создаёт пользователя (если нет), заполняет профиль и возвращает его."""
    user = find_user(token, email)
    if user is None:
        _request(
            "POST",
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/users",
            data={
                "username": email,
                "email": email,
                "enabled": True,
                "emailVerified": True,
                "firstName": email.split("@")[0],
                "lastName": "SSO",
            },
            token=token,
            as_json=True,
        )
        user = find_user(token, email)
        if user is None:
            sys.exit("Не удалось создать пользователя")
    # У созданных через admin-REST пользователей Keycloak может ставить
    # required action VERIFY_PROFILE — чистим, чтобы войти без лишнего шага.
    _request(
        "PUT",
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user['id']}",
        data={
            "firstName": email.split("@")[0],
            "lastName": "SSO",
            "requiredActions": [],
        },
        token=token,
        as_json=True,
    )
    return find_user(token, email) or user


def set_password(token: str, user: dict, password: str) -> None:
    """Устанавливает пароль пользователю (без требования менять)."""
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user['id']}/reset-password"
    payload = {"type": "password", "value": password, "temporary": False}
    _request("PUT", url, data=payload, token=token, as_json=True)


def grant_realm_role(token: str, user: dict, role: dict) -> None:
    """Назначает realm-роль пользователю."""
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user['id']}/role-mappings/realm"
    _request(
        "POST",
        url,
        data=[{"id": role["id"], "name": role["name"]}],
        token=token,
        as_json=True,
    )


def main() -> None:
    print(f"Жду Keycloak ({KEYCLOAK_URL})…")
    wait_for_ready()
    print("Keycloak готов, получаю токен админа…")
    token = admin_token()

    print(f"Проверяю realm-роль «{ADMIN_ROLE}»…")
    role = ensure_realm_role(token, ADMIN_ROLE)

    for account in ACCOUNTS:
        user = ensure_user(token, account["email"])
        set_password(token, user, account["password"])
        if account["role"] == ADMIN_ROLE:
            grant_realm_role(token, user, role)
        print(f"Готово: {account['email']} (роль {account['role']})")

    print()
    print("Учётные записи для SSO-входа:")
    for account in ACCOUNTS:
        print(f"    {account['email']:28} / {account['password']}")
    print()
    print("Откройте http://localhost:8000/auth/sso/start в браузере.")


if __name__ == "__main__":
    main()
