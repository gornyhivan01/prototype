"""Тесты cookie-сессии: CSRF, ротация refresh-токена и отзыв."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.helpers import DEFAULT_PASSWORD, auth_headers, register_user

CSRF_HEADER = "X-CSRF-Token"


async def _login(
    client: AsyncClient, email: str = "session@example.com", *, password: str = DEFAULT_PASSWORD
) -> dict[str, Any]:
    """Регистрирует пользователя и открывает cookie-сессию."""
    user = await register_user(client, email, password=password)
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {
        "user": user,
        "body": response.json(),
        "csrf": client.cookies.get("csrf_token"),
        "refresh": client.cookies.get("refresh_token"),
        "access": client.cookies.get("access_token"),
    }


async def test_profile_works_with_cookie_session(async_client: AsyncClient) -> None:
    """Профиль доступен по cookie, без заголовка Authorization."""
    session = await _login(async_client)

    response = await async_client.get("/auth/profile")

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "session@example.com"
    assert session["body"]["email"] == "session@example.com"


async def test_register_does_not_create_session(async_client: AsyncClient) -> None:
    """После регистрации сессии нет: нужен явный вход."""
    await register_user(async_client, "no-session@example.com")

    response = await async_client.get("/auth/profile")

    assert response.status_code == 401


async def test_unsafe_request_without_csrf_is_rejected(async_client: AsyncClient) -> None:
    """Запрос с cookie, но без CSRF-заголовка, отклоняется."""
    await _login(async_client)

    response = await async_client.post("/tasks", json={"title": "Без CSRF"})

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF-токен отсутствует или неверен"


async def test_unsafe_request_with_csrf_succeeds(async_client: AsyncClient) -> None:
    """С правильным CSRF-заголовком cookie-сессия может менять данные."""
    session = await _login(async_client)

    response = await async_client.post(
        "/tasks",
        json={"title": "С CSRF"},
        headers={CSRF_HEADER: session["csrf"]},
    )

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "С CSRF"


async def test_safe_request_does_not_need_csrf(async_client: AsyncClient) -> None:
    """GET-запросы CSRF-заголовка не требуют."""
    await _login(async_client)

    response = await async_client.get("/tasks")

    assert response.status_code == 200


async def test_refresh_rotates_token_and_reuse_revokes_all(async_client: AsyncClient) -> None:
    """Старый refresh-токен отзывается, повторное использование гасит все сессии."""
    session = await _login(async_client)
    old_refresh = session["refresh"]

    rotated = await async_client.post("/auth/refresh", headers={CSRF_HEADER: session["csrf"]})
    assert rotated.status_code == 200, rotated.text
    new_refresh = async_client.cookies.get("refresh_token")
    assert new_refresh and new_refresh != old_refresh
    # После ротации в cookie-jar лежит новый CSRF-токен — предъявляем его.
    current_csrf = async_client.cookies.get("csrf_token") or session["csrf"]

    # Повторно предъявляем уже отозванный токен — это признак кражи.
    reuse = await async_client.post(
        "/auth/refresh",
        cookies={"refresh_token": old_refresh},
        headers={CSRF_HEADER: current_csrf},
    )
    assert reuse.status_code == 401

    # После этого недействителен и новый токен: отозваны все сессии.
    after_reuse = await async_client.post(
        "/auth/refresh",
        cookies={"refresh_token": new_refresh},
        headers={CSRF_HEADER: session["csrf"]},
    )
    assert after_reuse.status_code == 401


async def test_reuse_is_written_to_audit(async_client: AsyncClient, admin_token: str) -> None:
    """Повторное использование токена попадает в журнал аудита."""
    session = await _login(async_client)
    old_refresh = session["refresh"]
    await async_client.post("/auth/refresh", headers={CSRF_HEADER: session["csrf"]})
    current_csrf = async_client.cookies.get("csrf_token") or session["csrf"]

    await async_client.post(
        "/auth/refresh",
        cookies={"refresh_token": old_refresh},
        headers={CSRF_HEADER: current_csrf},
    )

    response = await async_client.get(
        "/audit", params={"action": "auth.token.reused"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] >= 1


async def test_logout_revokes_session_and_clears_cookies(async_client: AsyncClient) -> None:
    """Выход отзывает refresh-токен, чистит cookie и пишет событие в аудит."""
    session = await _login(async_client)
    old_refresh = session["refresh"]

    response = await async_client.post("/auth/logout", headers={CSRF_HEADER: session["csrf"]})

    assert response.status_code == 204
    assert async_client.cookies.get("access_token") is None
    assert async_client.cookies.get("csrf_token") is None
    assert (await async_client.get("/auth/profile")).status_code == 401

    after_logout = await async_client.post(
        "/auth/refresh",
        cookies={"refresh_token": old_refresh},
        headers={CSRF_HEADER: session["csrf"]},
    )
    assert after_logout.status_code == 401


async def test_logout_is_written_to_audit(async_client: AsyncClient, admin_token: str) -> None:
    """Выход фиксируется как ``auth.logout``."""
    session = await _login(async_client)
    await async_client.post("/auth/logout", headers={CSRF_HEADER: session["csrf"]})

    response = await async_client.get(
        "/audit", params={"action": "auth.logout"}, headers=auth_headers(admin_token)
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items and items[0]["email"] == "session@example.com"


async def test_refresh_without_cookie_returns_401(async_client: AsyncClient) -> None:
    """Без refresh-cookie обновлять нечего."""
    response = await async_client.post("/auth/refresh")

    assert response.status_code == 401
    assert response.json()["detail"] == "Сессия недействительна"


async def test_refresh_token_is_stored_as_hash(async_client: AsyncClient) -> None:
    """В базе лежит SHA-256 токена, а не сам токен."""
    session = await _login(async_client)

    from sqlalchemy import select

    from src.core.database import async_session_factory
    from src.models.refresh_token import RefreshToken

    async with async_session_factory() as db:
        stored = await db.scalar(select(RefreshToken))

    assert stored is not None
    assert stored.token_hash != session["refresh"]
    assert len(stored.token_hash) == 64


async def test_deleted_user_session_stops_working(
    async_client: AsyncClient, app: FastAPI, admin_token: str
) -> None:
    """Удаление пользователя каскадно удаляет его сессии."""
    session = await _login(async_client, "deletable@example.com")

    # Админ действует отдельным Bearer-клиентом: в первом клиенте остаётся
    # cookie-сессия удаляемого пользователя, и она не должна подменять токен.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as admin_client:
        response = await admin_client.delete(
            f"/admin/users/{session['user']['id']}", headers=auth_headers(admin_token)
        )
        assert response.status_code == 204

    # Сессия удалённого пользователя отозвана каскадом (ON DELETE CASCADE).
    assert (await async_client.get("/auth/profile")).status_code == 401
