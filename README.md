# FastAPI + PostgreSQL + Alembic

[![CI](https://github.com/gornyhivan01/prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/gornyhivan01/prototype/actions/workflows/ci.yml)

Для знакомства с **FastAPI**, **PostgreSQL** и **Alembic**.
Пять ручек, две миграции, аутентификация по паролю с JWT и юнит-тесты.

## Что внутри

| Ручка | Назначение |
|---|---|
| `GET /health` | Проверка, что сервис жив |
| `POST /users` | Создание пользователя (пароль сохраняется как SHA-256-хеш) |
| `POST /auth/login` | Вход по email и паролю, выдача JWT |
| `GET /users/me` | Текущий пользователь (защищена, нужен JWT) |
| `GET /users/{id}` | Просмотр пользователя (чтение из PostgreSQL) |

Автоматические **Swagger UI** (`/docs`) и **OpenAPI** (`/openapi.json`).

## Стек

- FastAPI + Uvicorn
- SQLAlchemy 2.0 (синхронный) + драйвер `psycopg2`
- Alembic (миграции)
- PostgreSQL 16 (Docker Compose, порт **5433**)
- Пароли: SHA-256 через стандартный `hashlib`
- Токены: JWT (HS256) через `PyJWT`
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
(`401`, `404`, `409`, `422`).

## Аутентификация

1. **Регистрация.** `POST /users` принимает пароль (8–128 символов) и сохраняет
   только его SHA-256-хеш. В ответе и в базе исходного пароля нет.
2. **Вход.** `POST /auth/login` проверяет email и пароль и возвращает
   `access_token` (JWT) со сроком жизни `ACCESS_TOKEN_EXPIRE_MINUTES`
   (по умолчанию 30 минут). В ответе есть `expires_in` — тот же срок в секундах.
3. **Защищённая ручка.** `GET /users/me` читает заголовок
   `Authorization: Bearer <token>`, проверяет подпись и срок действия и
   возвращает владельца токена. Просроченный токен даёт `401`.

> **Почему SHA-256 — учебный компромисс.** Это быстрый хеш без соли: одинаковые
> пароли дают одинаковый хеш, а высокая скорость помогает перебору. В реальном
> проекте используйте Argon2id, bcrypt или PBKDF2 с большим числом итераций.
> В коде хеширование изолировано в `hash_password` и `verify_password`
> (`app/security.py`), поэтому алгоритм меняется одной правкой.

В Swagger UI удобно так: создайте пользователя, нажмите **Authorize**, введите
email в поле *username* и пароль — токен подставится в запросы автоматически.

```bash
# Регистрация
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email": "ivan.petrov@example.com", "full_name": "Иван Петров", "password": "secret123"}'

# Вход (форма OAuth2: username — это email)
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ivan.petrov@example.com&password=secret123"

# Защищённая ручка
curl http://localhost:8000/users/me -H "Authorization: Bearer <token>"
```

Пароль и токен — разные вещи: пароль проверяется один раз и не хранится в
открытом виде, а JWT клиент отправляет в каждом запросе. Подпись токена
проверяется ключом `SECRET_KEY`: без него токен не подделать, но и сервис не
запустится с чужим ключом.

> **Важно:** значение `SECRET_KEY` по умолчанию подходит только для локального
> запуска. В продакшене задайте случайную строку не короче 32 символов:
> `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Проверка ручек

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email": "ivan.petrov@example.com", "full_name": "Иван Петров", "password": "secret123"}'

curl http://localhost:8000/users/1
```

## Тесты и покрытие

Тесты юнит-уровня: вместо PostgreSQL используется SQLite в памяти, а зависимость
`get_db` подменяется через `app.dependency_overrides`. Docker для тестов не нужен.
Проверяются и успешные сценарии, и ошибки: неверный пароль, просроченный токен,
токен с несуществующим пользователем, отсутствие заголовка `Authorization`,
а также корректный срок жизни токена (`exp` и `expires_in`).

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
  config.py        # настройки (pydantic-settings), включая SECRET_KEY
  database.py      # движок, SessionLocal, зависимость get_db
  models.py        # модель User (email, имя, хеш пароля)
  schemas.py       # Pydantic-схемы (с примерами для Swagger)
  security.py      # хеширование паролей (SHA-256) и выпуск/проверка JWT
  dependencies.py  # зависимость get_current_user (Bearer-токен)
  routers/
    users.py       # POST /users, GET /users/me, GET /users/{id}
    auth.py        # POST /auth/login
  main.py          # создание приложения, GET /health
alembic/
  env.py           # окружение миграций (URL из настроек)
  versions/        # миграции: users, затем hashed_password
tests/             # юнит-тесты
```

## Для понимания

1. **FastAPI** собирает приложение в `app/main.py`, а ручки вынесены в
   `app/routers/users.py` и `app/routers/auth.py` через `APIRouter`.
2. **SQLAlchemy** описывает таблицу классом `User` (`app/models.py`).
   Схема БД создаётся **не** автоматически, а миграцией Alembic, изменения схемы версионируются.
3. **Alembic** читает строку подключения из настроек приложения (`app/config.py`),
   поэтому `DATABASE_URL` — единственный источник.
4. **Зависимость `get_db`** открывает и закрывает сессию на каждый запрос; в
   тестах она подменяется, что изолирует тесты от реальной БД.
5. **Пароли** хешируются SHA-256 без соли — так требует учебное задание. Это
   быстрый хеш, поэтому одинаковые пароли дают одинаковый результат, а перебор
   остаётся дешёвым; в продакшене нужен Argon2id/bcrypt/PBKDF2.
6. **JWT** — подписанный токен с полями `sub` (id пользователя), `iat` и `exp`.
   Сервер не хранит сессии: при каждом запросе он проверяет подпись и срок.
   Время жизни задаётся `ACCESS_TOKEN_EXPIRE_MINUTES`; значение `0` или меньше
   отклоняется при старте, чтобы нельзя было случайно выпускать мёртвые токены.
7. **`get_current_user`** — зависимость FastAPI: достаёт токен из заголовка,
   декодирует его и загружает пользователя из БД. Если токен неверный или
   пользователь удалён, возвращается `401`.
