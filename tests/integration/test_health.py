"""Интеграционные тесты служебных ручек."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(async_client: AsyncClient) -> None:
    """/health отвечает без авторизации."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_openapi_describes_routes(async_client: AsyncClient) -> None:
    """Схема OpenAPI собирается и содержит основные пути."""
    response = await async_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/auth/login" in paths
    assert "/tasks" in paths
    assert "/admin/users" in paths
