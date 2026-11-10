"""Закрывает все открытые PR репозитория prototype (для полной замены).

Токен берётся из переменной окружения GH_TOKEN (заполняется обёрткой
скрипта из `git credential fill`).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

REPO = "gornyhivan01/prototype"
API = "https://api.github.com"


def _headers() -> dict[str, str]:
    token = os.environ.get("GH_TOKEN", "")
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "prototype-replace",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    }


def _list_open() -> list[dict[str, object]]:
    url = f"{API}/repos/{REPO}/pulls?state=open&per_page=100"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _close(number: int) -> None:
    url = f"{API}/repos/{REPO}/pulls/{number}"
    data = json.dumps({"state": "closed"}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="PATCH", headers={**_headers(), "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"Ошибка закрытия PR #{number}: HTTP {exc.code} {exc.read().decode()[:200]}",
              file=sys.stderr)
        raise


def main() -> None:
    pulls = _list_open()
    print(f"Открытых PR: {len(pulls)}")
    for pr in pulls:
        number = int(pr["number"])  # type: ignore[arg-type]
        title = pr["title"]  # type: ignore[index]
        _close(number)
        print(f"PR #{number} закрыт: {title}")


if __name__ == "__main__":
    main()