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

from app.config import get_settings
from app.examples import HEALTH_EXAMPLE
from app.routers import auth, users

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

Учебный сервис с пятью ручками. Пользователи хранятся в PostgreSQL,
схема базы создаётся миграцией Alembic.

**Аутентификация:** `POST /auth/login` по паролю (Argon2id) и **SSO через
Keycloak** (`GET /auth/sso/start` → callback → свой JWT, редирект на дашборд
`/dashboard`). Парольный вход можно отключить переменной `SSO_ONLY=true`.

**Роли (RBAC):** `admin` создаёт пользователей и смотрит список, обычный
пользователь видит свой профиль. Роль при SSO приходит из Keycloak
(realm-роль `admin`), локально хранится в `users.role`.

**Аудит:** создание пользователя и попытки входа пишутся в таблицу
`audit_log` и дублируются в stdout. Пароли и токены в аудит не попадают.

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
| GET | `/users/me` | Текущий пользователь (нужен JWT) |
| GET | `/users/{user_id}` | Пользователь по id (админ или владелец) |

Страницы: `/` — вход через SSO, `/dashboard` — дашборд по роли.
""",
    openapi_tags=[
        {"name": "service", "description": "Служебные ручки: проверка живости сервиса."},
        {"name": "users", "description": "Создание и просмотр пользователей в PostgreSQL."},
        {"name": "auth", "description": "Аутентификация: по паролю и через SSO (Keycloak)."},
    ],
)

app.include_router(auth.router)
app.include_router(users.router)

# --- Простейший фронтенд (без сборки): лендинг и дашборд по роли ---
# Токен после SSO достигает дашборда через фрагмент URL (#access_token=…),
# JS кладёт его в sessionStorage и вызывает API того же порта.
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
