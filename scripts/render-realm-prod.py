#!/usr/bin/env python3
"""Готовит ``keycloak/realm-export.prod.json`` из dev-экспорта реалма.

Меняет только то, что зависит от окружения:

* ``redirectUris`` / ``webOrigins`` / ``post.logout.redirect.uris`` — на APP_URL;
* ``secret`` клиента — на KEYCLOAK_CLIENT_SECRET;
* включает brute-force protection.

Скрипт идемпотентен: читает исходный ``realm-export.json`` и каждый раз
перезаписывает ``realm-export.prod.json``. Прод-файл в git не хранится.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "keycloak" / "realm-export.json"
TARGET = ROOT / "keycloak" / "realm-export.prod.json"


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Не задана переменная окружения {name}")
    return value


def main() -> None:
    app_url = require("APP_URL").rstrip("/")
    client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "prototype-web")
    client_secret = require("KEYCLOAK_CLIENT_SECRET")

    realm = json.loads(SOURCE.read_text(encoding="utf-8"))
    realm["sslRequired"] = "external"
    realm["bruteForceProtected"] = True

    for client in realm.get("clients", []):
        if client.get("clientId") != client_id:
            continue
        client["secret"] = client_secret
        client["redirectUris"] = [f"{app_url}/auth/sso/callback"]
        client["webOrigins"] = [app_url]
        client.setdefault("attributes", {})["post.logout.redirect.uris"] = f"{app_url}/"
        break
    else:
        sys.exit(f"В {SOURCE.name} нет клиента {client_id!r}")

    TARGET.write_text(
        json.dumps(realm, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"готово: {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
