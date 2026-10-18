"""Тесты служебных эндпоинтов и документации."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """GET /health подтверждает, что сервис жив."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_is_available(client: TestClient) -> None:
    """Схема OpenAPI отдаётся по стандартному пути /openapi.json."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/users" in paths


def test_swagger_docs_is_available(client: TestClient) -> None:
    """Swagger UI доступен на /docs."""
    response = client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_has_russian_examples(client: TestClient) -> None:
    """В схеме есть русские описания, примеры запроса и примеры ответов."""
    spec = client.get("/openapi.json").json()

    post_users = spec["paths"]["/users"]["post"]
    assert post_users["summary"] == "Создать пользователя"

    body_examples = post_users["requestBody"]["content"]["application/json"]["examples"]
    assert "russian" in body_examples
    assert body_examples["russian"]["summary"] == "Пользователь с именем на русском"

    created = post_users["responses"]["201"]["content"]["application/json"]["example"]
    assert created["id"] == 1

    conflict = post_users["responses"]["409"]["content"]["application/json"]["example"]
    assert "email" in conflict["detail"]

    get_user = spec["paths"]["/users/{user_id}"]["get"]
    assert get_user["responses"]["404"]["description"] == "Пользователь с указанным id не найден"
    assert "example" in get_user["responses"]["200"]["content"]["application/json"]

    health = spec["paths"]["/health"]["get"]
    assert health["responses"]["200"]["content"]["application/json"]["example"] == {"status": "ok"}


def test_openapi_tags_have_russian_descriptions(client: TestClient) -> None:
    """Теги в /docs снабжены русскими описаниями."""
    spec = client.get("/openapi.json").json()

    tags = {tag["name"]: tag.get("description") for tag in spec["tags"]}
    assert tags["service"]
    assert tags["users"]
