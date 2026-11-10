"""Юнит-тесты классификации кэширования и CSP (без БД)."""

from __future__ import annotations

import pytest

from src.api.middleware import (
    CONTENT_SECURITY_POLICY,
    IMMUTABLE_CACHE,
    NO_STORE_CACHE,
    REVALIDATE_CACHE,
    cache_control,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/assets/index-BDDWRqVu.js", IMMUTABLE_CACHE),
        ("/assets/index-CqqI3JZH.css", IMMUTABLE_CACHE),
        ("/", REVALIDATE_CACHE),
        ("/index.html", REVALIDATE_CACHE),
        ("/favicon.ico", REVALIDATE_CACHE),
        ("/auth/login", NO_STORE_CACHE),
        ("/tasks", NO_STORE_CACHE),
        ("/admin/users", NO_STORE_CACHE),
        ("/audit/me", NO_STORE_CACHE),
        ("/health", NO_STORE_CACHE),
        ("/openapi.json", NO_STORE_CACHE),
        ("/docs", NO_STORE_CACHE),
    ],
)
def test_cache_control_by_path(path: str, expected: str) -> None:
    """Хешированные ассеты кэшируются надолго, API — никогда, остальное — no-cache."""
    assert cache_control(path) == expected


def test_csp_blocks_inline_scripts_and_frames() -> None:
    """Политика запрещает inline-скрипты, плагины и встраивание в iframe."""
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert "object-src 'none'" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "base-uri 'none'" in CONTENT_SECURITY_POLICY
