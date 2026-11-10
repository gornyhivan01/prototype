"""HTTP-заголовки безопасности и правила кэширования.

Middleware добавляет к каждому ответу защитные заголовки. Строгий CSP
применяется только к собственному интерфейсу и API: Swagger UI и ReDoc
подгружают скрипты и стили с CDN и содержат inline-скрипт инициализации,
поэтому для них CSP отключён.

Кэширование:
- файлы в ``/assets/`` содержат хеш в имени (``index-<hash>.js``) — их можно
  кэшировать навсегда;
- ``index.html`` и прочая статика без хеша — всегда ревалидируются;
- ответы API содержат данные пользователя, поэтому не кэшируются вовсе.
"""

from __future__ import annotations

import secrets

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER

# Методы, меняющие состояние: для них требуется CSRF-токен.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Вход и регистрация ещё не имеют cookie-сессии, /auth/token — только для Bearer.
CSRF_EXEMPT_PATHS = frozenset({"/auth/login", "/auth/register", "/auth/token"})

# Файлы Vite с хешем в имени не меняются, пока не изменится сборка.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
# index.html и статика без хеша: браузер обязан спросить сервер (304 дёшев).
REVALIDATE_CACHE = "no-cache"
# Ответы API содержат JWT-данные и историю действий — кэшировать нельзя.
NO_STORE_CACHE = "no-store"

# Префиксы API и служебной документации: ответы не кэшируются.
API_PREFIXES: tuple[str, ...] = (
    "/auth",
    "/tasks",
    "/admin",
    "/audit",
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
)

# Swagger UI/ReDoc используют CDN и inline-скрипт — под строгий CSP не подходят.
DOCS_PREFIXES: tuple[str, ...] = ("/docs", "/redoc", "/openapi.json")

# Интерфейс ходит только на свой origin и не использует inline-скрипты,
# поэтому 'unsafe-inline' не нужен.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def cache_control(path: str) -> str:
    """Возвращает значение ``Cache-Control`` для пути запроса."""
    if path.startswith("/assets/"):
        return IMMUTABLE_CACHE
    if path.startswith(API_PREFIXES):
        return NO_STORE_CACHE
    return REVALIDATE_CACHE


class SecurityHeadersMiddleware:
    """Добавляет защитные заголовки и ``Cache-Control`` к HTTP-ответам.

    Чистый ASGI-middleware, а не ``BaseHTTPMiddleware``: не мешает
    ``BackgroundTasks`` и потоковым ответам.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Frame-Options"] = "DENY"
                headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
                if not path.startswith(DOCS_PREFIXES):
                    headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
                headers["Cache-Control"] = cache_control(path)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _cookies_from_scope(scope: Scope) -> dict[str, str]:
    """Разбирает заголовок ``Cookie`` из ASGI-scope."""
    for name, value in scope["headers"]:
        if name != b"cookie":
            continue
        cookies: dict[str, str] = {}
        for part in value.decode("latin-1").split(";"):
            key, _, item = part.strip().partition("=")
            if key:
                cookies[key] = item
        return cookies
    return {}


def _header_from_scope(scope: Scope, name: bytes) -> str:
    """Возвращает значение первого заголовка с именем ``name``."""
    for header, value in scope["headers"]:
        if header == name:
            return value.decode("latin-1")
    return ""


class CSRFMiddleware:
    """Проверяет double-submit CSRF-токен.

    Проверка нужна только для запросов, аутентифицированных cookie: браузер
    прикладывает cookie сам, поэтому чужая страница может инициировать запрос.
    Запросы с Bearer-токеном CSRF не подвержены — им заголовок не нужен.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._is_violation(scope):
            response = JSONResponse(
                {"detail": "CSRF-токен отсутствует или неверен"}, status_code=403
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _is_violation(scope: Scope) -> bool:
        """Определяет, нарушает ли запрос защиту от CSRF."""
        if scope["method"] not in UNSAFE_METHODS:
            return False
        if scope["path"] in CSRF_EXEMPT_PATHS:
            return False

        cookies = _cookies_from_scope(scope)
        # Без access-cookie сессии нет: анонимный запрос или Bearer-токен.
        if ACCESS_COOKIE not in cookies:
            return False

        expected = cookies.get(CSRF_COOKIE, "")
        provided = _header_from_scope(scope, CSRF_HEADER.lower().encode("ascii"))
        if not expected or not provided:
            return True
        return not secrets.compare_digest(provided, expected)
