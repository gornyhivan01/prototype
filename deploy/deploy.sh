#!/usr/bin/env bash
# Деплой Prototype на одну VM.
#
#   ./deploy/deploy.sh              # обычный деплой (образ уже в registry)
#   SKIP_PULL=1 ./deploy/deploy.sh  # использовать локально собранный образ
#   BUILD=1 ./deploy/deploy.sh      # собрать образ на месте
#   ./deploy/deploy.sh --bootstrap  # один раз: создать первого админа в Keycloak
#
# Требуется заполненный .env (см. deploy/.env.prod.example).
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
    echo "Нет .env. Скопируйте deploy/.env.prod.example в .env и заполните." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

# Прод-реалм: адреса, секрет клиента, brute-force protection.
python3 scripts/render-realm-prod.py

COMPOSE=(docker compose --env-file .env -f docker-compose.prod.yml)

if [[ "${SKIP_PULL:-0}" != "1" ]]; then
    "${COMPOSE[@]}" pull
fi

if [[ "${BUILD:-0}" == "1" ]]; then
    "${COMPOSE[@]}" build app
fi

echo "→ запускаю postgres…"
"${COMPOSE[@]}" up -d --wait postgres

echo "→ применяю миграции…"
"${COMPOSE[@]}" run --rm --no-deps app alembic upgrade head

echo "→ запускаю сервисы…"
"${COMPOSE[@]}" up -d

if [[ "${1:-}" == "--bootstrap" ]]; then
    : "${BOOTSTRAP_ADMIN_EMAIL:?задайте BOOTSTRAP_ADMIN_EMAIL в .env}"
    : "${BOOTSTRAP_ADMIN_PASSWORD:?задайте BOOTSTRAP_ADMIN_PASSWORD в .env}"
    echo "→ создаю первого администратора в Keycloak…"
    "${COMPOSE[@]}" run --rm --no-deps \
        -e KEYCLOAK_URL=http://keycloak:8080 \
        app python scripts/keycloak-bootstrap.py
fi

echo "→ проверяю /health…"
for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T app \
        python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" \
        >/dev/null 2>&1; then
        echo "готово: ${APP_URL}"
        exit 0
    fi
    sleep 2
done

echo "health-check не прошёл" >&2
"${COMPOSE[@]}" ps
exit 1
