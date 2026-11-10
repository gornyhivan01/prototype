"""Тесты защитных HTTP-заголовков и правил кэширования."""

from __future__ import annotations

from httpx import AsyncClient

CSP_MARKER = "default-src 'self'"


async def test_api_responses_are_not_cached(async_client: AsyncClient) -> None:
    """Ответы API не попадают в кэш браузера и прокси."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


async def test_unauthorized_responses_are_not_cached(async_client: AsyncClient) -> None:
    """Даже отказ 401 помечается как некэшируемый."""
    response = await async_client.get("/tasks")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


async def test_index_is_revalidated(async_client: AsyncClient) -> None:
    """index.html нельзя кэшировать: в нём ссылки на новые хеши ассетов."""
    response = await async_client.get("/")

    assert response.headers["cache-control"] == "no-cache"


async def test_security_headers_are_present(async_client: AsyncClient) -> None:
    """Базовые защитные заголовки есть на любом ответе."""
    response = await async_client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert "geolocation=()" in response.headers["permissions-policy"]
    assert CSP_MARKER in response.headers["content-security-policy"]


async def test_docs_are_exempt_from_csp(async_client: AsyncClient) -> None:
    """Swagger UI грузит CDN и inline-скрипт, поэтому CSP для него отключён."""
    response = await async_client.get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    # Остальные заголовки действуют и на документацию.
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
