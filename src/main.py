"""Точка входа FastAPI-приложения."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.middleware import CSRFMiddleware, SecurityHeadersMiddleware
from src.api.routes import audit, auth, tasks, users
from src.core.config import get_settings
from src.core.exceptions import AppError

settings = get_settings()

# Собранный React-интерфейс (frontend/dist) кладётся в static/ при сборке образа.
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

# Уведомления и аудит пишутся в stdout через логгеры приложения.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description="""# Prototype

REST API для управления задачами: сессия в HttpOnly-cookie с CSRF-защитой,
Argon2id, RBAC (USER/ADMIN), PostgreSQL, Alembic и журнал аудита.

**Как попробовать:**

1. `POST /auth/register` — зарегистрируйтесь.
2. `POST /auth/login` — получите cookie-сессию (браузер) или
   `POST /auth/token` — access-токен для curl/Swagger и нажмите **Authorize**.
3. `POST /tasks` — создайте задачу, `GET /tasks` — посмотрите список.

Администратору доступны `GET /admin/users`, `PUT /admin/users/{id}/role`
и полный журнал `GET /audit`; свои события видны в `GET /audit/me`.
""",
    openapi_tags=[
        {"name": "service", "description": "Служебные ручки."},
        {"name": "auth", "description": "Регистрация, вход и профиль."},
        {"name": "tasks", "description": "CRUD задач."},
        {"name": "admin", "description": "Управление пользователями (ADMIN)."},
        {"name": "audit", "description": "Журнал действий: полный (ADMIN) и свои события."},
    ],
)

# Порядок важен: последний добавленный middleware — внешний, поэтому
# защитные заголовки попадут и в ответы CSRF-проверки.
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(audit.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Превращает доменные ошибки в HTTP-ответы."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["service"], summary="Проверка живости сервиса")
async def health() -> dict[str, str]:
    """Возвращает `ok`, если сервис запущен."""
    return {"status": "ok"}


# Интерфейс монтируется последним: API-маршруты выше имеют приоритет.
# SPA использует HashRouter, поэтому серверный fallback на index.html не нужен.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
