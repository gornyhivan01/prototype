"""Точка входа FastAPI-приложения.

Интерактивная документация: ``/docs`` (Swagger UI).
Машиночитаемая схема: ``/openapi.json``.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.examples import HEALTH_EXAMPLE
from app.routers import auth, users

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="""# FastAPI, PostgreSQL, Alembic

Учебный сервис с пятью ручками. Пользователи хранятся в PostgreSQL,
схема базы создаётся миграцией Alembic.

**Аутентификация:** пароль при регистрации превращается в Argon2id-хеш,
`POST /auth/login` выдаёт JWT (access-токен), а `GET /users/me` принимает его
в заголовке `Authorization: Bearer <token>`.

**Как попробовать:**

1. `POST /users` — создайте пользователя (пример уже подставлен).
2. `POST /auth/login` — войдите под его email и паролем либо нажмите
   **Authorize** и введите email в поле *username*.
3. `GET /users/me` — вызовите защищённую ручку: Swagger подставит токен сам.

**Список ручек:**

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | Проверка, что сервис жив |
| POST | `/users` | Создание пользователя (запись в PostgreSQL) |
| POST | `/auth/login` | Вход по email и паролю, выдача JWT |
| GET | `/users/me` | Текущий пользователь (нужен JWT) |
| GET | `/users/{user_id}` | Просмотр пользователя (чтение из PostgreSQL) |
""",
    openapi_tags=[
        {"name": "service", "description": "Служебные ручки: проверка живости сервиса."},
        {"name": "users", "description": "Создание и просмотр пользователей в PostgreSQL."},
        {"name": "auth", "description": "Аутентификация по паролю и выдача JWT."},
    ],
)

app.include_router(auth.router)
app.include_router(users.router)


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
