"""Точка входа FastAPI-приложения.

Интерактивная документация: ``/docs`` (Swagger UI).
Машиночитаемая схема: ``/openapi.json``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.config import get_settings
from app.examples import HEALTH_EXAMPLE
from app.routers import audit, auth, users

# Аудит пишется в stdout через logger "app.audit". basicConfig не перетирает
# настройки uvicorn, если обработчики уже добавлены.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="""# FastAPI, PostgreSQL, Alembic

Учебный сервис: пользователи в PostgreSQL (RBAC), вход по паролю и через **SSO
(Keycloak)**, аудит действий. Схема базы создаётся миграциями Alembic.

**Аутентификация:** `POST /auth/login` по паролю (Argon2id) и **SSO через
Keycloak** (`GET /auth/sso/start` → callback → свой JWT). Парольный вход можно
отключить переменной `SSO_ONLY=true`.

**Роли (RBAC):** `admin` управляет пользователями и смотрит полный журнал
аудита; обычный пользователь видит свой профиль и свои события аудита. Роль при
SSO приходит из Keycloak (realm-роль `admin`), локально хранится в `users.role`.

**Аудит:** создание/удаление пользователя и попытки входа пишутся в таблицу
`audit_log` и дублируются в stdout. Пароли и токены в аудит не попадают.
Журнал: `GET /audit` — весь (только admin), `GET /audit/me` — свои события.

**Как попробовать:**

1. `POST /users` — создайте пользователя (пример уже подставлен).
2. `POST /auth/login` — войдите под его email и паролем либо нажмите
   **Authorize** и введите email в поле *username*.
3. `GET /users/me` — вызовите защищённую ручку: Swagger подставит токен сам.

**Список ручек:**

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | Проверка, что сервис жив |
| POST | `/users` | Создание пользователя (**только admin**) |
| GET | `/users` | Список пользователей (**только admin**) |
| POST | `/auth/login` | Вход по email и паролю, выдача JWT |
| GET | `/auth/sso/start` | Вход через SSO (Keycloak), редирект в IdP |
| GET | `/auth/sso/callback` | Callback Keycloak: обмен кода на свой JWT |
| GET | `/auth/sso/logout` | Single logout: завершает SSO-сессию в Keycloak |
| GET | `/users/me` | Текущий пользователь (нужен JWT) |
| GET | `/users/{user_id}` | Пользователь по id (админ или владелец) |
| DELETE | `/users/{user_id}` | Удаление пользователя (**только admin**; себя удалить нельзя) |
| GET | `/audit` | Журнал аудита целиком (**только admin**) |
| GET | `/audit/me` | Свои события в журнале аудита |

**Фронтенд:** React SPA в `frontend/` (Vite + TypeScript). Страницы: `/` —
лендинг со входом через SSO, `/dashboard` — профиль и свои события аудита, а
для роли `admin` — управление пользователями и полный журнал аудита. Если SPA
не собран (`frontend/dist`), FastAPI отдаёт статический фолбэк из `app/static/`.
""",
    openapi_tags=[
        {"name": "service", "description": "Служебные ручки: проверка живости сервиса."},
        {"name": "users", "description": "Создание и просмотр пользователей в PostgreSQL."},
        {"name": "auth", "description": "Аутентификация: по паролю и через SSO (Keycloak)."},
        {
            "name": "audit",
            "description": "Журнал аудита: целиком — администратору, свои события — пользователю.",
        },
    ],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(audit.router)

# --- Фронтенд ---
# Прод: FastAPI отдаёт собранный React-SPA из frontend/dist, неизвестные пути
# (клиентский роутинг, например /dashboard) отдают index.html.
# Если сборки нет (dev/CI без Node), работает прежняя статика без сборки.
# Монтирование делается в конце файла, после всех API-маршрутов.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get(
    "/health",
    tags=["service"],
    summary="Проверка живости сервиса",
    description="""Возвращает `ok`, если сервис запущен.

**Пример запроса:**

```bash
curl http://localhost:8000/health
```
""",
    responses={
        200: {
            "description": "Сервис работает",
            "content": {"application/json": {"example": HEALTH_EXAMPLE}},
        }
    },
)
def health() -> dict[str, str]:
    """Возвращает ``ok``, если сервис запущен."""
    return {"status": "ok"}


class _SPAStaticFiles(StaticFiles):
    """Статика SPA: неизвестный путь отдаёт ``index.html`` (клиентский роутер)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


if (_FRONTEND_DIST / "index.html").is_file():
    # Прод/dev с собранным React (npm run build).
    app.mount("/", _SPAStaticFiles(directory=_FRONTEND_DIST, html=True), name="spa")
else:
    # Фолбэк без сборки: прежние статические страницы.
    _STATIC_DIR = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Лендинг с кнопкой «Войти через SSO»."""
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        """Дашборд: профиль (все) или управление пользователями (admin)."""
        return FileResponse(_STATIC_DIR / "dashboard.html")
