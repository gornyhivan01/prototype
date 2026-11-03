#!/usr/bin/env bash
# Выполняется один раз при создании пустого тома pgdata.
# Создаёт отдельную роль и БД для Keycloak, чтобы он не жил в БД приложения.
set -euo pipefail

: "${KEYCLOAK_DB_USER:?KEYCLOAK_DB_USER не задан}"
: "${KEYCLOAK_DB_PASSWORD:?KEYCLOAK_DB_PASSWORD не задан}"

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE ROLE "${KEYCLOAK_DB_USER}" LOGIN PASSWORD '${KEYCLOAK_DB_PASSWORD}';
        CREATE DATABASE keycloak OWNER "${KEYCLOAK_DB_USER}";
EOSQL
