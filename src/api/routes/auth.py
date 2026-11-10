"""Маршруты аутентификации.

Основной путь — cookie-сессия: access- и refresh-токены недоступны JavaScript
(``HttpOnly``), а CSRF защищён схемой double-submit. Для curl, CI и Swagger UI
оставлен ``POST /auth/token``, который возвращает access-токен в теле ответа.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from src.api.dependencies import CurrentUser, DbSession
from src.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from src.api.schemas.user import UserRead
from src.core.audit import client_ip
from src.core.config import get_settings
from src.core.cookies import REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from src.core.security import create_access_token
from src.services.session_service import SessionService
from src.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация пользователя",
)
async def register(payload: RegisterRequest, session: DbSession, request: Request) -> UserRead:
    """Создаёт пользователя с ролью USER. Сессия не создаётся — нужен вход."""
    service = UserService(session)
    user = await service.register(
        email=payload.email,
        password=payload.password,
        name=payload.name,
        ip_address=client_ip(request),
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=UserRead, summary="Вход: HttpOnly-cookie сессия")
async def login(
    payload: LoginRequest, session: DbSession, request: Request, response: Response
) -> UserRead:
    """Проверяет пароль и кладёт access/refresh/CSRF-токены в cookie."""
    user = await UserService(session).authenticate(
        email=payload.email,
        password=payload.password,
        ip_address=client_ip(request),
    )
    tokens = await SessionService(session).start(user=user)
    set_session_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        csrf_token=tokens.csrf_token,
        settings=get_settings(),
    )
    return UserRead.model_validate(user)


@router.post("/token", response_model=TokenResponse, summary="Access-токен для API-клиентов")
async def issue_token(payload: LoginRequest, session: DbSession, request: Request) -> TokenResponse:
    """Выдаёт access-токен в теле ответа: для curl, CI и Swagger UI.

    Браузерная часть приложения этой ручкой не пользуется.
    """
    user = await UserService(session).authenticate(
        email=payload.email,
        password=payload.password,
        ip_address=client_ip(request),
    )
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=UserRead, summary="Обновить сессию (ротация токена)")
async def refresh(request: Request, session: DbSession, response: Response) -> UserRead | Response:
    """Меняет refresh-токен на новый; при недействительном — очищает cookie."""
    settings = get_settings()
    token = request.cookies.get(REFRESH_COOKIE)
    rotated = (
        await SessionService(session).rotate(refresh_token=token, ip_address=client_ip(request))
        if token
        else None
    )
    if rotated is None:
        invalid = JSONResponse({"detail": "Сессия недействительна"}, status_code=401)
        clear_session_cookies(invalid, settings=settings)
        return invalid

    user, tokens = rotated
    set_session_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        csrf_token=tokens.csrf_token,
        settings=settings,
    )
    return UserRead.model_validate(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Выход: отзыв сессии и очистка cookie",
)
async def logout(request: Request, session: DbSession) -> Response:
    """Отзывает refresh-токен и удаляет cookie сессии."""
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await SessionService(session).revoke(refresh_token=token, ip_address=client_ip(request))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, settings=get_settings())
    return response


@router.get("/profile", response_model=UserRead, summary="Профиль текущего пользователя")
async def profile(current_user: CurrentUser) -> UserRead:
    """Возвращает профиль владельца cookie-сессии или Bearer-токена."""
    return UserRead.model_validate(current_user)
