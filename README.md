# Prototype

REST API для управления задачами: **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0
(async)**, **Alembic**, **JWT**, **Argon2id**, **React 18 + Vite + TypeScript**,
**Docker Compose**, **GitHub Actions**.

## Возможности

- регистрация, вход по email/паролю, профиль;
- JWT (HS256), RBAC: `USER` и `ADMIN`;
- CRUD задач с фильтрами по статусу, приоритету и дедлайну, пагинацией;
- архив задач удалённых пользователей (доступен только администратору);
- админка: список пользователей, создание, удаление, смена роли;
- **журнал аудита**: входы (успешные и неудачные), создание/удаление
  пользователей, смена ролей, действия с задачами; `/audit` — для ADMIN,
  `/audit/me` — свои события;
- фоновое «email»-уведомление о созданной задаче (заглушка в лог);
- SPA на React раздаётся тем же FastAPI, отдельный сервер и CORS не нужны.

## Архитектура

```mermaid
flowchart LR
    subgraph client["Клиент"]
        SPA["React SPA<br/>HashRouter + fetch"]
        DOCS["Swagger UI<br/>/docs"]
        CLI["curl / Postman"]
    end

    subgraph app["FastAPI (src/)"]
        ROUTES["Роуты<br/>auth · tasks · admin · audit · health"]
        DEPS["Зависимости<br/>JWT · RBAC · сессия БД"]
        SERVICES["Сервисы<br/>UserService · TaskService"]
        REPOS["Репозитории<br/>User · Task"]
        UOW["Unit of Work<br/>commit / rollback"]
        AUDIT["Аудит<br/>audit_log + stdout"]
        BG["BackgroundTasks<br/>«email» → лог"]
        STATIC["StaticFiles<br/>frontend/dist"]
    end

    PG[("PostgreSQL 16")]
    ALEMBIC["Alembic<br/>миграции"]

    SPA -->|"REST + HttpOnly-cookie<br/>+ X-CSRF-Token"| ROUTES
    DOCS --> ROUTES
    CLI --> ROUTES
    STATIC -->|"index.html + assets"| SPA
    ROUTES --> DEPS
    ROUTES --> SERVICES
    ROUTES -.->|"после ответа"| BG
    SERVICES --> REPOS
    SERVICES --> UOW
    SERVICES --> AUDIT
    REPOS -->|"SQLAlchemy async"| PG
    UOW --> PG
    AUDIT --> PG
    ALEMBIC -->|"upgrade head"| PG
```

Путь запроса:

1. SPA отправляет REST-запрос с cookie-сессией; unsafe-методы (`POST`, `PUT`,
   `PATCH`, `DELETE`) несут CSRF-токен в заголовке `X-CSRF-Token`. API-клиенты
   (curl, Swagger UI) ходят через `Authorization: Bearer <JWT>`.
2. Зависимости (`src/api/dependencies.py`) проверяют access-токен из cookie или
   заголовка и роль, затем открывают `AsyncSession`.
3. Роут вызывает сервис, сервис — репозиторий и `UnitOfWork`; событие аудита
   добавляется в ту же сессию и коммитится вместе с действием.
4. После ответа `BackgroundTasks` пишет «письмо» о созданной задаче в лог.
5. Схему БД накатывает Alembic при старте контейнера.

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.12, FastAPI 0.115, Uvicorn |
| БД | PostgreSQL 16, SQLAlchemy 2.0 (async), asyncpg, Alembic |
| Аутентификация | JWT HS256 (`PyJWT`), пароли — Argon2id (`pwdlib`) |
| Тесты | pytest, pytest-asyncio, Testcontainers (PostgreSQL), coverage |
| Frontend | React 18, React Router 7, TypeScript 5, Vite 8 |
| Инфраструктура | Docker, Docker Compose, GitHub Actions, uv |

## Быстрый старт (Docker)

```bash
cp .env.example .env
docker compose up -d --build
```

Поднимутся PostgreSQL и приложение, применятся миграции Alembic.
Интерфейс: <http://localhost:8000/>, Swagger UI: <http://localhost:8000/docs>.

Остановить: `docker compose down` (с данными — `docker compose down -v`).

## Запуск без Docker

```bash
cp .env.example .env          # DATABASE_URL должен указывать на ваш PostgreSQL
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
```

### Разработка интерфейса

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, запросы к API проксируются на 8000
```

Сборка статики (её же делает `Dockerfile` в первом stage):

```bash
cd frontend
npm run build      # dist/ -> в образе /app/static
```

## Эндпоинты

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| GET | `/health` | публичный | Проверка живости |
| POST | `/auth/register` | публичный | Регистрация (роль USER) |
| POST | `/auth/login` | публичный | Вход: сессия в HttpOnly-cookie |
| POST | `/auth/token` | публичный | Access-токен для curl/Swagger UI (в теле) |
| POST | `/auth/refresh` | cookie сессии | Ротация refresh-токена, обновление access |
| POST | `/auth/logout` | cookie сессии | Выход: отзыв сессии и очистка cookie |
| GET | `/auth/profile` | авторизованный | Профиль текущего пользователя |
| GET | `/tasks` | авторизованный | Список задач (пагинация, фильтры) |
| POST | `/tasks` | авторизованный | Создать задачу + «email» |
| GET | `/tasks/{task_id}` | авторизованный | Задача по id |
| PATCH | `/tasks/{task_id}` | авторизованный | Обновить задачу |
| DELETE | `/tasks/{task_id}` | авторизованный | Удалить задачу |
| GET | `/admin/users` | ADMIN | Список пользователей |
| POST | `/admin/users` | ADMIN | Создать пользователя с любой ролью |
| DELETE | `/admin/users/{user_id}` | ADMIN | Удалить пользователя (задачи → в архив) |
| PATCH | `/admin/users/{user_id}/role` | ADMIN | Сменить роль |
| GET | `/audit` | ADMIN | Журнал аудита целиком |
| GET | `/audit/me` | авторизованный | Свои события |

**Права:** пользователь видит и меняет только свои задачи; администратор —
все задачи, управление пользователями и ролями, полный журнал аудита.

**Архив.** При удалении пользователя его задачи не пропадают: они помечаются
архивными (`archived_at`, `archived_owner_email`) и остаются доступны
администратору через `GET /tasks?archived=true`. Удалить себя и последнего
администратора нельзя (400).

## Аудит

Действия фиксируются в таблице `audit_log` и дублируются в stdout
(logger `app.audit`). Пароли и JWT в журнал не попадают.

| Событие | Когда пишется |
|---|---|
| `user.created` | регистрация или создание пользователя админом |
| `user.deleted` | удаление пользователя (в `details` — число задач в архиве) |
| `user.role_changed` | смена роли (`from` / `to`) |
| `auth.login.success` | успешный вход |
| `auth.login.failed` | неверный email или пароль (`details.reason`) |
| `auth.logout` | выход (отзыв сессии) |
| `auth.token.reused` | повторное предъявление отозванного refresh-токена — отозваны все сессии (`details.revoked_sessions`) |
| `task.created` | создание задачи |
| `task.updated` | изменение задачи (`details.fields` — имена полей) |
| `task.deleted` | удаление задачи |

**Просмотр.** `GET /audit` (только ADMIN) отдаёт весь журнал,
`GET /audit/me` — события текущего пользователя: его действия и события о его
учётке. Обе ручки возвращают `{total, limit, offset, items}` (новые первыми),
фильтр `action` и пагинацию `limit` (1–200, по умолчанию 50) / `offset`.
В полном журнале есть ещё фильтр `email` (подстрока).

```bash
# Полный журнал (только ADMIN):
curl 'http://localhost:8000/audit?action=auth.login.success&limit=20' \
  -H 'Authorization: Bearer <admin-token>'

# Свои события (любая роль):
curl 'http://localhost:8000/audit/me?limit=20' \
  -H 'Authorization: Bearer <token>'
```

Запись аудита добавляется в ту же транзакцию, что и действие: «пользователь
создан, а события нет» не бывает. При удалении пользователя `actor_id` и
`target_user_id` обнуляются (`ON DELETE SET NULL`), но сама история остаётся.

## Кэширование

Приложение не кэширует ответы на уровне бизнес-логики: данные персонализированы,
а PostgreSQL и так держит горячие страницы в памяти. Настроены только
HTTP-правила (`src/api/middleware.py`):

| Путь | `Cache-Control` | Почему |
|---|---|---|
| `/assets/*` | `public, max-age=31536000, immutable` | в имени файла хеш сборки Vite |
| `/` и прочая статика | `no-cache` | `index.html` ссылается на новые хеши ассетов |
| API и документация | `no-store` | ответы содержат данные пользователя |

`StaticFiles` дополнительно отдаёт `ETag`/`Last-Modified`, поэтому повторные
запросы статики получают `304 Not Modified`. Redis не используется: сессии
stateless (JWT), фоновых очередей нет, объём данных невелик.

## Безопасность

- Пароли — **Argon2id** (`pwdlib`), у каждого пароля своя соль.
- Прозрачная миграция: bcrypt-хеши прежних версий принимаются при входе
  и сразу пересчитываются в Argon2id (`needs_rehash`).
- **Cookie-сессия.** Access- и refresh-токены живут в `HttpOnly`-cookie
  (`SameSite=strict`, `Path=/auth` у refresh) — JavaScript их не читает, XSS их
  не украдёт. CSRF-токен отдаётся отдельной cookie и повторяется в заголовке
  `X-CSRF-Token` (double-submit); проверяется только при наличии access-cookie,
  поэтому Bearer-клиенты заголовок не шлют.
- Access-токен — короткий JWT HS256 (`sub`, `iat`, `exp`), срок по умолчанию
  **15 минут**. Refresh-токен — случайная строка; в БД лежит только её SHA-256,
  срок **7 дней** (`REFRESH_TOKEN_EXPIRE_DAYS`).
- **Ротация и отзыв.** Каждый `POST /auth/refresh` меняет refresh-токен: старый
  отзывается, выдаётся новый. Повторное предъявление отозванного токена
  трактуется как кража — отзываются все сессии пользователя (событие
  `auth.token.reused`). Выход (`POST /auth/logout`) отзывает текущую сессию.
- Заголовки ответа: `Content-Security-Policy` (без `unsafe-inline`),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY`, `Permissions-Policy`. Для Swagger UI (`/docs`,
  `/redoc`) CSP отключён: они грузят CDN и inline-скрипт.
- Для curl/CI/Swagger оставлен `POST /auth/token`, возвращающий access-токен
  в теле ответа.
- В продакшене задайте случайный `SECRET_KEY` и `COOKIE_SECURE=true` (HTTPS):
  `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Тесты

```bash
uv sync
uv run pytest -q
```

Интеграционные тесты поднимают `postgres:16-alpine` через Testcontainers,
накатывают миграции Alembic и очищают таблицы перед каждым тестом. Запросы идут
в приложение через `ASGITransport`, без сети.

Если Docker недоступен, укажите готовую базу:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5433/app uv run pytest -q
```

Покрытие проверяется в CI с порогом **75%**:

```bash
uv run pytest --cov-fail-under=75
```

Что покрыто: регистрация/вход/профиль (включая bcrypt → Argon2id), CRUD задач,
RBAC, архивирование задач, админские ручки, фильтры и пагинация, журнал аудита
(события, «мои события», фильтры, изоляция чужих записей, сохранение истории
после удаления пользователя), JWT и валидация схем.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) запускается на push
в `main`/`master`, на каждый PR и вручную:

| Job | Что проверяет |
|---|---|
| `quality` | `ruff check`, `black --check`, `pytest` с порогом покрытия **75%** на сервисе PostgreSQL |
| `frontend` | `npm ci` и `npm run build` (проверка типов + сборка Vite) |
| `docker` | сборка образа (`uv sync --locked` + node-стадия), импорт приложения, `/health` и отдача SPA |

Пуш образа в реестр и автодеплой не выполняются.

## Структура

```
src/
  api/
    routes/          # auth, tasks, users (admin), audit
    schemas/         # Pydantic-схемы
    dependencies.py  # JWT, RBAC, сессия БД
  core/
    config.py        # pydantic-settings
    security.py      # Argon2id, bcrypt-совместимость, PyJWT
    audit.py         # события аудита: запись в БД и stdout
    database.py      # async-движок, session factory
    exceptions.py
  models/            # User, Task, AuditLog
  repositories/      # доступ к данным
  services/          # бизнес-логика, уведомления
  utils/             # unit_of_work
  main.py
frontend/            # React + Vite + TypeScript (src/api, src/auth, src/pages)
alembic/             # миграции: users/tasks → архив → audit_log
tests/               # unit- и интеграционные тесты
Dockerfile           # node-стадия + uv --locked, непривилегированный пользователь
```

## Первый администратор

Регистрация всегда создаёт `USER`. Первого администратора назначьте вручную
(см. также готовый скрипт `scripts/create_admin.py`):

```bash
docker compose exec db psql -U app -d app \
  -c "UPDATE users SET role='ADMIN' WHERE email='admin@example.com';"
```

После этого вход тем же email даёт админские права (`GET /admin/users`,
`PATCH /admin/users/{id}/role`, `GET /audit`).

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | PostgreSQL для compose |
| `DATABASE_URL` | `postgresql+asyncpg://…` (в Docker — внутренний адрес `db:5432`) |
| `SECRET_KEY` | секрет подписи JWT — заменить в проде |
| `JWT_ALGORITHM` | алгоритм подписи (по умолчанию HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | срок жизни access-токена (по умолчанию 15) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | срок жизни refresh-токена (по умолчанию 7) |
| `COOKIE_SECURE` | `true` на HTTPS (cookie только по TLS) |
| `COOKIE_SAMESITE` | `strict` (по умолчанию) / `lax` / `none` |
| `DEBUG` | SQL-эхо и режим отладки |
