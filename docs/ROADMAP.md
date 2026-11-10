# Состояние проекта и план

Документ для продолжения работы: что готово, какие решения приняты и что делать
дальше.

## Готово

**Каркас.** `src/{api,core,models,repositories,services,utils}`,
Alembic, Docker, React SPA, тесты на Testcontainers.

**Этап 1. Безопасность и аудит.**

- Пароли — Argon2id (`pwdlib`); bcrypt-хеши прежних версий принимаются и
  пересчитываются при входе.
- JWT — `PyJWT`.
- Аудит: `audit_log`, `user.created`, `user.deleted`, `user.role_changed`,
  `auth.login.success`, `auth.login.failed`, `auth.logout`, `auth.token.reused`,
  `task.created`, `task.updated`, `task.deleted`.
- API журнала: `GET /audit` (ADMIN), `GET /audit/me` (свои события), фильтры
  `action`/`email`, пагинация.
- Dockerfile на `uv sync --locked`; `requirements.txt` и Redis удалены.
- CI: `ruff`, `black --check`, `pytest --cov-fail-under=75`, сборка SPA и
  smoke-тест контейнера.
- SPA: страница «Журнал аудита» / «Мои действия».

**Этап 2. API задач.**

| Метод | Путь | Доступ |
|---|---|---|
| POST | `/auth/register` | публичный |
| POST | `/auth/login` | публичный |
| POST | `/auth/token` | публичный (access-токен для API-клиентов) |
| POST | `/auth/refresh` | cookie сессии |
| POST | `/auth/logout` | cookie сессии |
| GET | `/auth/profile` | авторизованный |
| GET/POST | `/tasks` | авторизованный |
| GET/PATCH/DELETE | `/tasks/{task_id}` | авторизованный |
| GET | `/admin/users` | ADMIN |
| POST | `/admin/users` | ADMIN |
| DELETE | `/admin/users/{user_id}` | ADMIN |
| PATCH | `/admin/users/{user_id}/role` | ADMIN |
| GET | `/audit` | ADMIN |
| GET | `/audit/me` | авторизованный |
| GET | `/health` | публичный |

**Этап 3. Тесты.**

- `tests/conftest.py`: PostgreSQL через Testcontainers (или `TEST_DATABASE_URL`),
  миграции Alembic, очистка `audit_log, tasks, users` перед тестом.
- `tests/integration/`: auth, tasks, admin, audit.
- `tests/unit/`: Argon2id, bcrypt-совместимость, JWT, схемы.
- Покрытие проверяется в CI с порогом 75%.

**Этап 4. Cookie-сессия.**

- Access/refresh-токены — в `HttpOnly`-cookie (`SameSite=strict`), CSRF —
  double-submit (`X-CSRF-Token`); `POST /auth/token` оставлен для curl/Swagger.
- Refresh-токен — случайная строка, в БД SHA-256 (`refresh_tokens`); ротация
  при каждом обновлении, отзыв при выходе; повторное предъявление отозванного
  токена отзывает все сессии (`auth.token.reused`).
- SPA: `credentials: same-origin`, тихий refresh по 401 с единственной
  параллельной попыткой; `localStorage` убран.
- Миграция `0004_refresh_tokens`; тесты `tests/integration/test_sessions.py`.

## Принятые решения

- Роли — `USER`/`ADMIN`, в БД строка + CHECK.
- Пароли — Argon2id; bcrypt только для чтения легаси-хешей.
- JWT — `PyJWT`, HS256, `sub` = id пользователя.
- Аудит пишется в той же транзакции, что и действие; при удалении пользователя
  ссылки `actor_id`/`target_user_id` обнуляются, история остаётся.
- Аудит задач пишет только имена изменённых полей: `details` — JSON, значения
  с `datetime` туда не сериализуются.
- Только локальный JWT, без внешнего IdP.
- Redis не нужен: фоновые уведомления — `BackgroundTasks` + логгер.
- Docker использует `uv sync --locked`, единственный манифест — `pyproject.toml`.
- Тестовая схема создаётся только миграциями Alembic, не `create_all`.
- Весь прогон идёт в одном event loop (`loop_scope = session`), чтобы пул
  asyncpg не переезжал между циклами.
- Фронтенд — React 18 / Vite 8 / React Router 7 / TS 5, `HashRouter`,
  сессия в `HttpOnly`-cookie + CSRF (без `localStorage`).
- `SecurityHeadersMiddleware` ставит CSP и защитные заголовки, а также
  `Cache-Control`: `immutable` для `/assets/*`, `no-cache` для `index.html`,
  `no-store` для API. Для `/docs` CSP отключён из-за CDN и inline-скрипта.

## Как запустить

```bash
docker compose up -d --build  # app + postgres, миграции при старте
docker compose down -v        # остановить и удалить данные
# Интерфейс: http://localhost:8000/   Swagger: http://localhost:8000/docs
```

Локально: `uv sync && uv run alembic upgrade head && uv run uvicorn src.main:app --reload`.

Тесты: `uv run pytest -q` (нужен Docker) или `TEST_DATABASE_URL=… uv run pytest -q`.

## Дальше

- Прод-контур (отдельный compose, reverse-proxy, скрипт раскатки) — при
  необходимости.
- Внешний IdP (OIDC) — отдельным этапом, если появится требование.
- Redis + Celery для реальных уведомлений вместо логгера.
