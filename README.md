# FastAPI + PostgreSQL + Alembic

[![CI](https://github.com/gornyhivan01/prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/gornyhivan01/prototype/actions/workflows/ci.yml)

Для знакомства с **FastAPI**, **PostgreSQL** и **Alembic**.
Три ручки, одна миграция и юнит-тесты.

## Что внутри

| Ручка | Назначение |
|---|---|
| `GET /health` | Проверка, что сервис жив |
| `POST /users` | Создание пользователя (запись в PostgreSQL) |
| `GET /users/{id}` | Просмотр пользователя (чтение из PostgreSQL) |

Автоматические **Swagger UI** (`/docs`) и **OpenAPI** (`/openapi.json`).

## Стек

- FastAPI + Uvicorn
- SQLAlchemy 2.0 (синхронный) + драйвер `psycopg2`
- Alembic (миграции)
- PostgreSQL 16 (Docker Compose, порт **5433**)
- Тесты: pytest + pytest-cov, SQLite в памяти

## Быстрый старт

```bash
# 1. Зависимости
uv sync

# 2. Конфигурация
cp .env.example .env

# 3. PostgreSQL
docker compose up -d postgres

# 4. Миграции
uv run alembic upgrade head

# 5. Запуск сервиса
uv run uvicorn app.main:app --reload
```

Открыть:
- документация — http://localhost:8000/docs
- схема OpenAPI — http://localhost:8000/openapi.json

В Swagger UI у каждой ручки приведены примеры на русском: описание с командой
`curl`, готовые примеры тела запроса, а также примеры успешных ответов и ошибок
(`404`, `409`, `422`).

## Проверка ручек

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email": "ivan.petrov@example.com", "full_name": "Иван Петров"}'

curl http://localhost:8000/users/1
```

## Тесты и покрытие

Тесты юнит-уровня: вместо PostgreSQL используется SQLite в памяти, а зависимость
`get_db` подменяется через `app.dependency_overrides`. Docker для тестов не нужен.

```bash
uv run pytest                  # запуск + отчёт о покрытии
uv run pytest --cov-report=html # HTML-отчёт в htmlcov/
```

Проверка качества:

```bash
uv run ruff check .
uv run black --check .
```

## Структура

```
app/
  config.py      # настройки (pydantic-settings)
  database.py    # движок, SessionLocal, зависимость get_db
  models.py      # модель User
  schemas.py     # Pydantic-схемы (с примерами для Swagger)
  routers/
    users.py     # POST /users, GET /users/{id}
  main.py        # создание приложения, GET /health
alembic/
  env.py         # окружение миграций (URL из настроек)
  versions/      # миграции
tests/           # юнит-тесты
```

## Для понимания

1. **FastAPI** собирает приложение в `app/main.py`, а ручки вынесены в
   `app/routers/users.py` через `APIRouter`.
2. **SQLAlchemy** описывает таблицу классом `User` (`app/models.py`).
   Схема БД создаётся **не** автоматически, а миграцией Alembic, изменения схемы версионируются.
3. **Alembic** читает строку подключения из настроек приложения (`app/config.py`),
   поэтому `DATABASE_URL` — единственный источник.
4. **Зависимость `get_db`** открывает и закрывает сессию на каждый запрос; в
   тестах она подменяется, что изолирует тесты от реальной БД.
