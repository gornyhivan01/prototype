"""Аутентификация: пароль (POST /auth/login) и SSO через Keycloak.

SSO-поток — гибридный: браузер аутентифицируется в Keycloak, а наш сервис
выпускает собственный JWT (как при парольном входе). Подробности протокола
— в :mod:`app.sso`.
"""

from __future__ import annotations

import html
import secrets
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import sso as sso_module
from app.audit import AuditAction, add_entry, log_entry, log_rejection
from app.config import get_settings
from app.database import get_db
from app.examples import (
    INVALID_CREDENTIALS_RESPONSE,
    TOKEN_EXAMPLE,
    VALIDATION_RESPONSE,
)
from app.models import ROLE_ADMIN, ROLE_USER, AuditLog, User
from app.schemas import Token
from app.security import create_access_token, hash_password, needs_rehash, verify_password
from app.sso import SsoError

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


def _sso_only_guard() -> None:
    """Возвращает 403, если сервис переведён в режим «только SSO»."""
    if get_settings().sso_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Парольный вход отключён: используйте SSO (/auth/sso/start)",
        )


def _name_from_claims(claims: dict[str, Any]) -> str:
    """Собирает отображаемое имя из claims IdP (не доверяем ни одному полю)."""
    name = claims.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()[:200]
    parts = [claims.get("given_name"), claims.get("family_name")]
    joined = " ".join(str(part).strip() for part in parts if isinstance(part, str) and part.strip())
    if joined:
        return joined[:200]
    username = claims.get("preferred_username")
    if isinstance(username, str) and username.strip():
        return username.strip()[:200]
    return str(claims.get("sub", "sso-user"))[:200]


def _error_page(message: str) -> str:
    """Страница ошибки SSO (без внутренних деталей)."""
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Вход через SSO</title></head>
<body>
<h1>Не удалось войти через SSO</h1>
<p>{html.escape(message)}</p>
<p><a href="/auth/sso/start">Попробовать ещё раз</a></p>
<p><a href="/docs">Открыть Swagger</a></p>
</body></html>"""


def _role_from_claims(claims: dict[str, Any]) -> str:
    """Выводит роль из claims Keycloak (realm-роль ``admin``, иначе ``user``).

    Роли приходят в ``realm_access.roles`` стандартного клиентского скоупа
    ``roles``: ``["default-roles-prototype", "offline_access", ..., "admin"]``.
    """
    realm_access = claims.get("realm_access") or {}
    realm_roles = realm_access.get("roles") or claims.get("roles") or []
    if ROLE_ADMIN in realm_roles:
        return ROLE_ADMIN
    return ROLE_USER


def _role_from_claims_if_admin(claims: dict[str, Any]) -> str | None:
    """Для существующего пользователя: повышение до админа, но не понижение.

    Источник истины ролей при SSO — Keycloak: если Keycloak наделил ролью
    ``admin``, локальная роль обновляется. Отсутствие роли администратора не
    отнимает её у пользователя, созданного раньше (например, другим способом).
    """
    role = _role_from_claims(claims)
    return ROLE_ADMIN if role == ROLE_ADMIN else None


def _dashboard_redirect_page(token: str) -> str:
    """Страница-мост: показывает токен и сразу перенаправляет на дашборд.

    Токен передаётся дашборду во фрагменте URL (``#access_token=…``):
    фрагмент не отправляется на сервер и не попадает в логи Access Log,
    поэтому это безопаснее, чем строка запроса. Дашборд читает его в JS.
    """
    escaped = html.escape(token)
    dashboard_url = f"/dashboard#access_token={quote(token, safe='')}"
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Вход выполнен</title>
<meta http-equiv="refresh" content="0; url={html.escape(dashboard_url, quote=True)}">
<script>window.location.replace("{html.escape(dashboard_url, quote=True)}");</script>
</head>
<body>
<h1>✅ Вход через SSO выполнен</h1>
<p>Перенаправляем на дашборд… Если ничего не произошло:
<a href="/dashboard">откройте дашборд вручную</a>.</p>
<details><summary>Показать access-токен</summary>
<textarea id="token" readonly rows="4" style="width:95%;word-break:break-all">{escaped}</textarea>
</details>
</body></html>"""


@router.post(
    "/login",
    response_model=Token,
    summary="Войти по email и паролю и получить JWT",
    description="""Проверяет email и пароль и возвращает access-токен.

**В Swagger UI:** нажмите **Authorize**, введите email в поле *username*,
пароль — в поле *password*, затем **Authorize**. Токен подставится в запросы
автоматически.

**Пример запроса:**

```bash
curl -X POST http://localhost:8000/auth/login \\
  -H 'Content-Type: application/x-www-form-urlencoded' \\
  -d 'username=ivan.petrov@example.com&password=secret123'
```

Неверный email и неверный пароль дают одинаковый ответ `401`, чтобы нельзя было
проверить существование пользователя.

**SSO.** Вход разрешён и через Keycloak: `GET /auth/sso/start`. Если сервис
переведён в режим «только SSO» (`SSO_ONLY=true`), этот эндпоинт вернёт `403`.

**Время жизни.** Токен действует `ACCESS_TOKEN_EXPIRE_MINUTES` минут (по
умолчанию 30). Срок записан в claim `exp`; после него сервер вернёт `401`, и
нужно войти заново. Ответ содержит `expires_in` — тот же срок в секундах.

**Аудит.** Успешная и неуспешная попытки входа пишутся в таблицу `audit_log`
и в лог приложения; пароль и токен туда не попадают.
""",
    responses={
        200: {
            "description": "Токен выдан",
            "content": {"application/json": {"example": TOKEN_EXAMPLE}},
        },
        401: INVALID_CREDENTIALS_RESPONSE,
        403: {"description": "Парольный вход отключён (режим «только SSO»)"},
        422: VALIDATION_RESPONSE,
    },
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    request: Request,
) -> Token:
    """Проверяет пароль и возвращает JWT."""
    _sso_only_guard()
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        entry = add_entry(
            db,
            action=AuditAction.LOGIN_FAILED,
            email=form.username,
            request=request,
            details={"reason": "unknown_email" if user is None else "invalid_password"},
        )
        db.commit()
        log_entry(entry)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if needs_rehash(user.hashed_password):
        # Прозрачная миграция: старый хеш (например, SHA-256) заменяется
        # на Argon2id в момент успешного входа.
        user.hashed_password = hash_password(form.password)

    entry = add_entry(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=user.id,
        target_user_id=user.id,
        email=user.email,
        request=request,
    )
    db.commit()
    log_entry(entry)

    return Token(
        access_token=create_access_token(subject=str(user.id)),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


@router.get(
    "/sso/start",
    summary="Войти через SSO (Keycloak)",
    description="""Перенаправляет браузер в Keycloak для входа.

Защита: `state` (анти-CSRF), `nonce` (анти-replay) и PKCE S256. После входа
Keycloak вернёт браузер на `/auth/sso/callback`, где сервис выпустит свой JWT.

**Обычный поток:** откройте `http://localhost:8000/auth/sso/start` в браузере.
""",
    responses={
        302: {"description": "Перенаправление в Keycloak"},
        503: {"description": "Сервис настроен без Keycloak (SSO_ENABLED=false)"},
    },
)
def sso_start() -> RedirectResponse:
    """Строит URL авторизации и перенаправляет в Keycloak."""
    settings = get_settings()
    if not settings.sso_enabled:
        raise HTTPException(status_code=503, detail="SSO отключён")
    url, _state = sso_module.create_authorization_url()
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/sso/callback",
    include_in_schema=False,
    summary="Callback Keycloak после SSO-входа",
    description="""Принимает код авторизации от Keycloak, обменивает его на
токены, проверяет `id_token` и выпускает свой JWT.""",
)
def sso_callback(
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Финальный шаг SSO: код авторизации -> свой JWT."""
    if error:
        log_rejection(
            action="auth.sso.failed",
            email=None,
            request=request,
            reason=f"idp_error={error}",
        )
        return HTMLResponse(_error_page("Провайдер вернул ошибку"), status_code=400)
    if not code or not state:
        log_rejection(
            action="auth.sso.failed",
            email=None,
            request=request,
            reason="missing_code_or_state",
        )
        return HTMLResponse(_error_page("Некорректный ответ провайдера"), status_code=400)

    try:
        claims = sso_module.exchange_id_token_claims(
            code=code, state=state, request_url=str(request.url)
        )
    except SsoError as exc:
        log_rejection(
            action="auth.sso.failed",
            email=None,
            request=request,
            reason="token_validation_failed",
        )
        return HTMLResponse(_error_page(str(exc)), status_code=400)

    email = (claims.get("email") or "").strip().lower()
    if not email:
        log_rejection(
            action="auth.sso.failed",
            email=None,
            request=request,
            reason="no_email_in_token",
        )
        return HTMLResponse(_error_page("IdP не вернул email"), status_code=400)

    user = db.scalar(select(User).where(User.email == email))
    entries: list[AuditLog] = []
    if user is None:
        # SSO-пользователь без пароля: в БД нужен валидный хеш, поэтому
        # кладём необратимый случайный. Войти по паролю такой пользователь
        # не сможет (это и требуется в гибридной схеме).
        user = User(
            email=email,
            full_name=_name_from_claims(claims),
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role=_role_from_claims(claims),
        )
        db.add(user)
        db.flush()
        entries.append(
            add_entry(
                db,
                action=AuditAction.USER_CREATED,
                target_user_id=user.id,
                email=email,
                request=request,
                details={"via": "sso", "role": user.role},
            )
        )
    else:
        new_role = _role_from_claims_if_admin(claims)
        if new_role is not None and user.role != new_role:
            user.role = new_role

    entries.append(
        add_entry(
            db,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id=user.id,
            target_user_id=user.id,
            email=user.email,
            request=request,
            details={"via": "sso", "role": user.role},
        )
    )
    db.commit()
    for entry in entries:
        log_entry(entry)

    token = create_access_token(subject=str(user.id))
    return HTMLResponse(_dashboard_redirect_page(token))
