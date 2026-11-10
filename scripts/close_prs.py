"""Закрывает открытые pull request репозитория prototype через GitHub API.

Токен берётся из переменной окружения ``GH_TOKEN`` (её заполняет обёртка
скрипта из ``git credential fill``). Утилита перечисляет открытые PR
и закрывает их — используется при полной замене содержимого репозитория.
"""

from __future__ import annotations

import os

import httpx

REPO = "gornyhivan01/prototype"
API = "https://api.github.com"


def _headers() -> dict[str, str]:
    """Заголовки с Bearer-токеном, если он задан."""
    token = os.environ.get("GH_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "prototype-tools"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def main() -> None:
    with httpx.Client(base_url=API, headers=_headers(), timeout=30) as client:
        response = client.get(f"/repos/{REPO}/pulls", params={"state": "open", "per_page": 100})
        response.raise_for_status()
        pulls = response.json()

        print(f"Открытых PR: {len(pulls)}")
        for pr in pulls:
            number = int(pr["number"])
            closed = client.patch(f"/repos/{REPO}/pulls/{number}", json={"state": "closed"})
            closed.raise_for_status()
            print(f"PR #{number} закрыт: {pr['title']}")


if __name__ == "__main__":
    main()
