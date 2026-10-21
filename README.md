# FastAPI + PostgreSQL + Alembic

[![CI](https://github.com/gornyhivan01/prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/gornyhivan01/prototype/actions/workflows/ci.yml)

Для знакомства с **FastAPI**, **PostgreSQL** и **Alembic**.
Пять ручек, три миграции, аутентификация по паролю с JWT, аудит и юнит-тесты.

## Что внутри

| Ручка | Назначение |
|---|---|
| `GET /health` | Проверка, что сервис жив |
| `POST /users` | Создание пользователя (пароль сохраняется как Argon2id-хеш) |
| `POST /auth/login` | Вход по email и паролю, выдача JWT |
| `GET /users/me` | Текущий пользователь (защищена, нужен JWT) |
| `GET /users/{id}` | Просмотр пользователя (чтение из PostgreSQL) |

Автоматические **Swagger UI** (`/docs`) и **OpenAPI** (`/openapi.json`).

Создание пользователя и попытки входа пишутся в таблицу `audit_log` и в лог
приложения — см. раздел [«Аудит»](#аудит).

## Стек

- FastAPI + Uvicorn
- SQLAlchemy 2.0 (синхронный) + драйвер `psycopg2`
- Alembic (миграции)
- PostgreSQL 16 (Docker Compose, порт **5433**)
- Пароли: Argon2id через `pwdlib`
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
   только его Argon2id-хеш. В ответе и в базе исходного пароля нет.
2. **Вход.** `POST /auth/login` проверяет email и пароль и возвращает
   `access_token` (JWT) со сроком жизни `ACCESS_TOKEN_EXPIRE_MINUTES`
   (по умолчанию 30 минут). В ответе есть `expires_in` — тот же срок в секундах.
3. **Защищённая ручка.** `GET /users/me` читает заголовок
   `Authorization: Bearer <token>`, проверяет подпись и срок действия и
   возвращает владельца токена. Просроченный токен даёт `401`.

> **Почему Argon2id.** У каждого пароля своя соль, поэтому одинаковые пароли
> дают разные хеши. Argon2id намеренно требует много памяти и времени, что
> делает перебор по украденной базе дорогим. Это рекомендованный алгоритм для
> паролей; в коде он изолирован в `hash_password` и `verify_password`
> (`app/security.py`).

> **Прозрачная миграция.** Если в базе остались хеши от прежней версии
> (например, SHA-256), они принимаются при входе и сразу пересчитываются
> в Argon2id. После первого успешного входа пользователя в базе хранится
> только Argon2id.

В Swagger UI удобно так: создайте пользователя, нажмите **Authorize**, введите
email в поле *username* и пароль — токен подставится в запросы автоматически.

Пароль и токен — разные вещи: пароль проверяется один раз и не хранится в
открытом виде, а JWT клиент отправляет в каждом запросе. Подпись токена
проверяется ключом `SECRET_KEY`: без него токен не подделать, но и сервис не
запустится с чужим ключом.

> **Важно:** значение `SECRET_KEY` по умолчанию подходит только для локального
> запуска. В продакшене задайте случайную строку не короче 32 символов:
> `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`.

Пошаговые команды с ожидаемыми ответами — в разделе [«Проверка»](#проверка).

## Проверка

### 1. Сервис жив

```bash
curl -s http://localhost:8000/health
# {"status":"ok"}
```

### 2. Регистрация и хранение пароля

```bash
curl -s -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email": "ivan.petrov@example.com", "full_name": "Иван Петров", "password": "secret123"}'
# {"id":1,"email":"ivan.petrov@example.com","full_name":"Иван Петров","created_at":"..."}
```

В ответе нет ни пароля, ни хеша. Посмотрим, что лежит в PostgreSQL:

```bash
docker compose exec postgres psql -U app -d app \
  -c "SELECT email, left(hashed_password, 12) AS prefix, length(hashed_password) AS len FROM users;"
```

Хеш начинается с `$argon2id$` и занимает около 97 символов. Соль у каждого
пароля своя, поэтому два пользователя с одинаковым паролем получат разные
хеши — проверить пароль можно только через `POST /auth/login`.

### 3. Вход и защищённая ручка

```bash
# Логин: сохраняем токен в переменную окружения
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ivan.petrov@example.com&password=secret123" | jq -r .access_token)

# Если jq не установлен:
# TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
#   -H "Content-Type: application/x-www-form-urlencoded" \
#   -d "username=ivan.petrov@example.com&password=secret123" \
#   | uv run python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/users/me -H "Authorization: Bearer $TOKEN"
# {"id":1,"email":"ivan.petrov@example.com","full_name":"Иван Петров","created_at":"..."}
```

Проверка ошибок:

```bash
# Неверный пароль → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ivan.petrov@example.com&password=wrong-password"
# 401

# Без токена → 401
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/users/me
# 401
```

### 4. Срок жизни токена

Ответ логина содержит `expires_in`:

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ivan.petrov@example.com&password=secret123" | uv run python -m json.tool
# {
#   "access_token": "eyJ...",
#   "token_type": "bearer",
#   "expires_in": 1800
# }
```

Тот же срок записан в самом токене (`exp - iat`):

```bash
export TOKEN
uv run python - <<'PY'
import base64
import json
import os

payload = os.environ["TOKEN"].split(".")[1]
payload += "=" * (-len(payload) % 4)
data = json.loads(base64.urlsafe_b64decode(payload))
print("iat:", data["iat"], "exp:", data["exp"])
print("срок жизни, сек:", data["exp"] - data["iat"])
PY
# срок жизни, сек: 1800
```

Как увидеть отказ по истечении:

```bash
# 1. В .env поставьте ACCESS_TOKEN_EXPIRE_MINUTES=1 и перезапустите сервис.
# 2. Войдите заново и получите TOKEN (как в шаге 3).
# 3. Подождите ~70 секунд и повторите запрос:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/users/me \
  -H "Authorization: Bearer $TOKEN"
# 401 — токен просрочен, нужно войти заново
```

## Аудит

Действия пользователей фиксируются в таблице `audit_log` и дублируются в
stdout (logger `app.audit`).

| Событие | Когда пишется | `actor_id` |
|---|---|---|
| `user.created` | успешная регистрация | сам пользователь |
| `auth.login.success` | успешный вход | пользователь |
| `auth.login.failed` | неверный email или пароль | `NULL` |

Для неудачного входа в `details` хранится причина: `{"reason": "unknown_email"}`
или `{"reason": "invalid_password"}`. Повторная регистрация на занятый email
в БД не пишется (транзакция откатывается), но оставляет warning в логе с
`reason=duplicate_email`.

Состав записи: `action`, `actor_id`, `target_user_id`, `email`, `ip_address`,
`details` (JSON), `created_at`. Пароли и JWT не логируются.

```sql
SELECT created_at, action, actor_id, email, ip_address, details
FROM audit_log
ORDER BY id DESC
LIMIT 20;
```

Пример строки в логе:

```text
2026-10-21 17:45:00,123 INFO app.audit: audit action=user.created actor_id=1 target_user_id=1 email=ivan.petrov@example.com ip=127.0.0.1
```

IP берётся из `request.client.host`; за reverse-proxy здесь будет адрес прокси,
поэтому для реального IP нужен разбор `X-Forwarded-For` с доверенным списком.

Событие `user.deleted` зарезервировано в `AuditAction`: ручка удаления пока не
добавлена, но таблица готова хранить историю и после удаления пользователя
(`actor_id` и `target_user_id` обнуляются по `ON DELETE SET NULL`).

## Тесты и покрытие

Тесты юнит-уровня: вместо PostgreSQL используется SQLite в памяти, а зависимость
`get_db` подменяется через `app.dependency_overrides`. Docker для тестов не нужен.
Проверяются и успешные сценарии, и ошибки: неверный пароль, просроченный токен,
токен с несуществующим пользователем, отсутствие заголовка `Authorization`,
корректный срок жизни токена (`exp` и `expires_in`), разные хеши для
одинаковых паролей (соль Argon2id), а также аудит: запись в БД, лог и
отсутствие пароля/токена в событиях.

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
  models.py        # модели User и AuditLog (email, имя, хеш пароля)
  schemas.py       # Pydantic-схемы (с примерами для Swagger)
  security.py      # хеширование паролей (Argon2id) и выпуск/проверка JWT
  audit.py         # события аудита: запись в БД и дублирование в stdout
  dependencies.py  # зависимость get_current_user (Bearer-токен)
  routers/
    users.py       # POST /users, GET /users/me, GET /users/{id}
    auth.py        # POST /auth/login
  main.py          # создание приложения, GET /health
alembic/
  env.py           # окружение миграций (URL из настроек)
  versions/        # миграции: users, hashed_password, audit_log
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
5. **Пароли** хешируются Argon2id: у каждого пароля своя соль, поэтому
   одинаковые пароли дают разные хеши, а параметры (память и итерации)
   делают перебор дорогим. Восстановить исходный пароль из хеша нельзя.
6. **JWT** — подписанный токен с полями `sub` (id пользователя), `iat` и `exp`.
   Сервер не хранит сессии: при каждом запросе он проверяет подпись и срок.
   Время жизни задаётся `ACCESS_TOKEN_EXPIRE_MINUTES`; значение `0` или меньше
   отклоняется при старте, чтобы нельзя было случайно выпускать мёртвые токены.
7. **`get_current_user`** — зависимость FastAPI: достаёт токен из заголовка,
   декодирует его и загружает пользователя из БД. Если токен неверный или
   пользователь удалён, возвращается `401`.
8. **Аудит** пишется в ту же транзакцию, что и действие: запись `user.created`
   добавляется в сессию до `commit`, поэтому не бывает «пользователь создан,
   а события нет». Для входа транзакция отдельная; неудачная попытка тоже
   сохраняется, чтобы были видны попытки подбора.
