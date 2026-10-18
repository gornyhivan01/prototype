"""Точка входа FastAPI-приложения.

Интерактивная документация: ``/docs`` (Swagger UI).
Машиночитаемая схема: ``/openapi.json``.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.examples import HEALTH_EXAMPLE
from app.routers import users

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="""# FastAPI, PostgreSQL, Alembic

Учебный сервис с тремя ручками. Пользователи хранятся в PostgreSQL,
схема базы создаётся миграцией Alembic.

**Как попробовать:**

1. Раскройте нужную ручку ниже.
2. Нажмите **Try it out**.
3. Примеры данных уже подставлены — нажмите **Execute**.

**Список ручек:**

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | Проверка, что сервис жив |
| POST | `/users` | Создание пользователя (запись в PostgreSQL) |
| GET | `/users/{user_id}` | Просмотр пользователя (чтение из PostgreSQL) |
""",
    openapi_tags=[
        {"name": "service", "description": "Служебные ручки: проверка живости сервиса."},
        {"name": "users", "description": "Создание и просмотр пользователей в PostgreSQL."},
    ],
)

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
