"""Точка входа FastAPI-приложения.

Интерактивная документация: ``/docs`` (Swagger UI).
Машиночитаемая схема: ``/openapi.json``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

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

**Аутентификация:** пароль при регистрации превращается в Argon2id-хеш,
`POST /auth/login` выдаёт JWT (access-токен), а `GET /users/me` принимает его
в заголовке `Authorization: Bearer <token>`.

**SSO через Keycloak:** вход «в один клик» через `GET /auth/sso/start` —
браузер перенаправляется в Keycloak (`http://localhost:8080`), а после входа
сервис выпускает свой JWT. Парольный вход при этом продолжает работать
(гибридная схема); отключить его можно переменной `SSO_ONLY=true`.

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
| POST | `/users` | Создание пользователя (запись в PostgreSQL) |
| POST | `/auth/login` | Вход по email и паролю, выдача JWT |
| GET | `/auth/sso/start` | Вход через SSO (Keycloak), редирект в IdP |
| GET | `/auth/sso/callback` | Callback Keycloak: обмен кода на свой JWT |
| GET | `/users/me` | Текущий пользователь (нужен JWT) |
| GET | `/users/{user_id}` | Просмотр пользователя (чтение из PostgreSQL) |
""",
    openapi_tags=[
        {"name": "service", "description": "Служебные ручки: проверка живости сервиса."},
        {"name": "users", "description": "Создание и просмотр пользователей в PostgreSQL."},
        {"name": "auth", "description": "Аутентификация: по паролю и через SSO (Keycloak)."},
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
