"""Заголовки кэширования: статика SPA и API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import _SPAStaticFiles


def _spa_client(tmp_path: Path) -> TestClient:
    """Мини-приложение с такой же раздачей SPA, как в проде."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><div id='root'></div>",
        encoding="utf-8",
    )
    (dist / "assets" / "app-abc123.js").write_text(
        "console.log(1)",
        encoding="utf-8",
    )
    app = FastAPI()
    app.mount("/", _SPAStaticFiles(directory=dist, html=True), name="spa")
    return TestClient(app)


def test_spa_index_is_revalidated(tmp_path: Path) -> None:
    response = _spa_client(tmp_path).get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_spa_fallback_is_revalidated(tmp_path: Path) -> None:
    response = _spa_client(tmp_path).get("/dashboard")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_immutable(tmp_path: Path) -> None:
    response = _spa_client(tmp_path).get("/assets/app-abc123.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_api_responses_are_not_stored(client: TestClient) -> None:
    for path in ("/health", "/users/me", "/audit", "/audit/me"):
        response = client.get(path)
        assert response.headers["cache-control"] == "no-store", path


def test_openapi_is_revalidated(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
