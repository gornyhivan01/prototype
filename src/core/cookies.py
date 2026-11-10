"""Cookie-сессия: установка и удаление HttpOnly-cookie.

Access- и refresh-токены недоступны JavaScript (``HttpOnly``), поэтому XSS
не может их прочитать. CSRF-токен, наоборот, читается фронтендом и повторяется
в заголовке ``X-CSRF-Token`` — это схема double-submit cookie.
"""

from __future__ import annotations

from starlette.responses import Response

from src.core.config import Settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

# Refresh-cookie отправляется только на /auth/*: остальные запросы её не видят.
REFRESH_COOKIE_PATH = "/auth"


def set_session_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    """Кладёт токены сессии в cookie с нужными атрибутами."""
    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 24 * 3600
    common = {"secure": settings.cookie_secure, "samesite": settings.cookie_samesite}

    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=access_max_age,
        httponly=True,
        path="/",
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        path=REFRESH_COOKIE_PATH,
        **common,
    )
    # CSRF-токен читается JavaScript, поэтому HttpOnly для него не ставится.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        path="/",
        **common,
    )


def clear_session_cookies(response: Response, *, settings: Settings) -> None:
    """Удаляет все cookie сессии (выход или недействительный refresh-токен)."""
    for name, path in (
        (ACCESS_COOKIE, "/"),
        (REFRESH_COOKIE, REFRESH_COOKIE_PATH),
        (CSRF_COOKIE, "/"),
    ):
        response.delete_cookie(
            name,
            path=path,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
