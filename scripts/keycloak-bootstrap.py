#!/usr/bin/env python3
"""Создаёт тестового пользователя SSO в реалме ``prototype`` Keycloak.

Запуск (после ``docker compose up -d keycloak``):

    python scripts/keycloak-bootstrap.py

Скрипт идемпотентен: повторный запуск не создаёт дублей, а сбрасывает пароль.

Использует только стандартную библиотеку (urllib) — без внешних зависимостей.
После выполнения войти в SSO можно под:
    sso.user@example.com / password123
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK_URL = "http://localhost:8080"
REALM = "prototype"

# Данные dev-пользователя Keycloak. Пароль только для локального стенда.  # noqa: S105
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"  # noqa: S105 — dev-админ Keycloak (docker-compose)
SSO_EMAIL = "sso.user@example.com"
SSO_PASSWORD = "password123"  # noqa: S105 — dev-пользователь реалма prototype
SSO_FIRST_NAME = "SSO"
SSO_LAST_NAME = "User"


class Unreachable(Exception):
    """Keycloak ещё не поднялся (или недоступен)."""


def _request(
    method: str,
    url: str,
    *,
    data: dict | None = None,
    token: str | None = None,
    as_json: bool = False,
) -> dict:
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
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        sys.exit(f"Не удалось получить токен админа: {exc}")
    return response["access_token"]


def find_user(token: str, email: str) -> dict | None:
    """Ищет пользователя по email в реалме ``prototype``."""
    query = urllib.parse.urlencode({"email": email, "exact": "true"})
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?{query}"
    users = _request("GET", url, token=token)
    return users[0] if users else None


def create_user(token: str, email: str) -> dict:
    """Создаёт пользователя и возвращает его."""
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users"
    payload = {
        "username": email,
        "email": email,
        "enabled": True,
        "emailVerified": True,
        "firstName": SSO_FIRST_NAME,
        "lastName": SSO_LAST_NAME,
    }
    _request("POST", url, data=payload, token=token, as_json=True)
    return find_user(token, email)


def set_password(token: str, user_id: str, password: str) -> None:
    """Устанавливает пароль пользователю (без требования менять)."""
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/reset-password"
    payload = {"type": "password", "value": password, "temporary": False}
    _request("PUT", url, data=payload, token=token, as_json=True)


def main() -> None:
    print(f"Жду Keycloak ({KEYCLOAK_URL})…")
    wait_for_ready()
    print("Keycloak готов, получаю токен админа…")
    token = admin_token()

    print(f"Нахожу/создаю пользователя {SSO_EMAIL}…")
    user = find_user(token, SSO_EMAIL)
    if user is None:
        user = create_user(token, SSO_EMAIL)
        print("Пользователь создан.")
    else:
        print("Пользователь уже существует.")

    print("Устанавливаю пароль…")
    set_password(token, user["id"], SSO_PASSWORD)

    print()
    print("Готово. Вход через SSO:")
    print(f"    email:    {SSO_EMAIL}")
    print(f"    password: {SSO_PASSWORD}")
    print()
    print("Откройте http://localhost:8000/auth/sso/start в браузере.")


if __name__ == "__main__":
    main()
